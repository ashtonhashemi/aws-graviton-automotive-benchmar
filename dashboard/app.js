const $ = id => document.getElementById(id);
const apiBase = $('apiBase');
const token = $('token');
const globalStatus = $('globalStatus');
const runStatus = $('runStatus');

function storageGet(key) {
  try { return window.sessionStorage ? sessionStorage.getItem(key) : null; }
  catch { return null; }
}

function storageSet(key, value) {
  try { if (window.sessionStorage) sessionStorage.setItem(key, value); }
  catch { /* storage may be blocked; dashboard still works */ }
}

if (!apiBase || !token) throw new Error('Dashboard HTML is incomplete. Redeploy dashboard files.');

apiBase.value = (window.APP_CONFIG && window.APP_CONFIG.apiBase) || storageGet('apiBase') || '';
token.value = storageGet('adminToken') || '';

function setStatus(message, type='info') {
  if (globalStatus) {
    globalStatus.textContent = message;
    globalStatus.className = `status-banner ${type}`;
  }
  if (runStatus) runStatus.textContent = message;
  console.log(`[dashboard:${type}] ${message}`);
}

function cfg() {
  const base = apiBase.value.trim().replace(/\/$/, '');
  const t = token.value.trim();
  if (!base) throw new Error('API URL is missing. Redeploy/update the dashboard or enter it above.');
  if (!t) throw new Error('Enter the dashboard admin token, then click Use configuration.');
  return { base, t };
}

async function call(path, options={}) {
  const {base,t} = cfg();
  let r;
  try {
    r = await fetch(base + path, {
      ...options,
      headers: {'content-type':'application/json','x-admin-token':t,...(options.headers||{})}
    });
  } catch (e) {
    throw new Error(`Network/API request failed: ${e.message}`);
  }
  const text = await r.text();
  let body = {};
  if (text) {
    try { body = JSON.parse(text); }
    catch { body = {error:text}; }
  }
  if (!r.ok) throw new Error(body.error || `API returned HTTP ${r.status}`);
  return body;
}

$('saveConfig').onclick = async () => {
  storageSet('apiBase', apiBase.value.trim());
  storageSet('adminToken', token.value.trim());
  setStatus('Configuration accepted. Checking AWS worker status…', 'working');
  await refresh();
};

async function refresh() {
  try {
    setStatus('Checking AWS worker status…', 'working');
    const s = await call('/status');
    $('x86State').textContent = s.x86_64.state;
    $('x86Type').textContent = `${s.x86_64.instance_type} · ${s.x86_64.architecture}`;
    $('armState').textContent = s.arm64.state;
    $('armType').textContent = `${s.arm64.instance_type} · ${s.arm64.architecture}`;
    setStatus(`Connected. x86: ${s.x86_64.state} · Graviton: ${s.arm64.state}`, 'success');
  } catch (e) { setStatus(e.message, 'error'); }
}

async function fleetAction(action) {
  try {
    setStatus(`${action === 'start' ? 'Starting' : 'Stopping'} both AWS workers…`, 'working');
    await Promise.all([
      call(`/instances/x86_64/${action}`, {method:'POST'}),
      call(`/instances/arm64/${action}`, {method:'POST'})
    ]);
    setStatus(`${action} requested for both workers.`, 'success');
    setTimeout(refresh, 3000);
  } catch(e) { setStatus(e.message, 'error'); }
}

$('startBoth').onclick = () => fleetAction('start');
$('stopBoth').onclick = () => fleetAction('stop');
$('refresh').onclick = refresh;

document.querySelectorAll('[data-arch]').forEach(b => b.onclick = async () => {
  try {
    setStatus(`${b.dataset.action === 'start' ? 'Starting' : 'Stopping'} ${b.dataset.arch}…`, 'working');
    await call(`/instances/${b.dataset.arch}/${b.dataset.action}`, {method:'POST'});
    setStatus(`${b.dataset.action} requested for ${b.dataset.arch}.`, 'success');
    setTimeout(refresh, 3000);
  } catch(e) { setStatus(e.message, 'error'); }
});

function verdict(v) { return v ? 'PASS' : 'FAIL'; }

function fmvssRow(name, r) {
  const m = r.result;
  return `<tr><td>${name}</td><td>${m.yaw_ratio_1s_pct}% (${verdict(m.stability_1s_pass)})</td><td>${m.yaw_ratio_1_75s_pct}% (${verdict(m.stability_1_75s_pass)})</td><td>${m.lateral_displacement_1_07s_m} m (${verdict(m.responsiveness_pass)})</td><td>${verdict(m.simulated_fmvss126_pass)}</td></tr>`;
}

function computeRow(name, r) {
  return `<tr><td>${name}</td><td>${r.median_wall_seconds}s</td><td>${Number(r.throughput_records_per_sec).toLocaleString()}</td><td>${r.median_cpu_seconds}s</td><td>${Number(r.max_rss_kb).toLocaleString()} KB</td></tr>`;
}

async function poll(runId) {
  for (let i=0; i<120; i++) {
    try {
      const r = await call(`/benchmark/results/${runId}`);
      if (r.complete) {
        $('results').innerHTML = fmvssRow('x86_64', r.x86_64) + fmvssRow('ARM64 / Graviton', r.arm64);
        $('computeResults').innerHTML = computeRow('x86_64', r.x86_64) + computeRow('ARM64 / Graviton', r.arm64);
        $('comparison').textContent = `ESC: ${String(r.run.esc).toUpperCase()} · Functional result match: ${r.comparison.functional_results_match ? 'YES' : 'NO'} · ARM/x86 throughput ratio: ${r.comparison.arm_vs_x86_throughput_ratio}× · Faster compute: ${r.comparison.faster_architecture}`;
        setStatus(`ESC SIL run ${runId} complete.`, 'success');
        return;
      }
      setStatus(`ESC SIL run ${runId} is executing…`, 'working');
    } catch (e) {
      setStatus(e.message, 'error');
      return;
    }
    await new Promise(resolve => setTimeout(resolve, 5000));
  }
  setStatus('Timed out waiting for results.', 'error');
}

$('run').onclick = async () => {
  try {
    setStatus('Submitting FMVSS 126-inspired ESC SIL workload to both workers…', 'working');
    const body = {
      records:Number($('records').value),
      iterations:Number($('iterations').value),
      mode:$('mode').value,
      esc:$('esc').value,
      auto_stop:$('autoStop').checked
    };
    const r = await call('/benchmark/run', {method:'POST', body:JSON.stringify(body)});
    setStatus(`Started ESC SIL run ${r.run_id}`, 'working');
    poll(r.run_id);
  } catch(e) { setStatus(e.message, 'error'); }
};

setStatus('Dashboard JavaScript loaded. Enter/confirm the admin token and click Use configuration.', 'info');
if (apiBase.value && token.value) refresh();
