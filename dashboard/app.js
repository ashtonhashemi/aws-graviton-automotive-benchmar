const $ = id => document.getElementById(id);
const apiBase = $('apiBase');
const token = $('token');
const globalStatus = $('globalStatus');

apiBase.value = window.APP_CONFIG?.apiBase || sessionStorage.getItem('apiBase') || '';
token.value = sessionStorage.getItem('adminToken') || '';

function setStatus(message, type='info') {
  globalStatus.textContent = message;
  globalStatus.className = `status-banner ${type}`;
}

function cfg() {
  const base = apiBase.value.trim().replace(/\/$/, '');
  const t = token.value.trim();
  if (!base) throw new Error('API URL is missing. Redeploy/update the dashboard or enter the API URL above.');
  if (!t) throw new Error('Enter the dashboard admin token, then click Use configuration.');
  return { base, t };
}

async function call(path, options={}) {
  const {base,t} = cfg();
  let r;
  try {
    r = await fetch(base + path, {
      ...options,
      headers: {
        'content-type':'application/json',
        'x-admin-token':t,
        ...(options.headers||{})
      }
    });
  } catch (e) {
    throw new Error(`Network/API request failed: ${e.message}`);
  }

  const text = await r.text();
  let body = {};
  if (text) {
    try { body = JSON.parse(text); }
    catch { body = { error: text }; }
  }
  if (!r.ok) throw new Error(body.error || `API returned HTTP ${r.status}`);
  return body;
}

$('saveConfig').onclick = async () => {
  sessionStorage.setItem('apiBase', apiBase.value.trim());
  sessionStorage.setItem('adminToken', token.value.trim());
  setStatus('Configuration saved. Checking AWS worker status…', 'working');
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
    const summary = `Connected. x86: ${s.x86_64.state} · Graviton: ${s.arm64.state}`;
    setStatus(summary, 'success');
    $('runStatus').textContent = summary;
  } catch (e) {
    setStatus(e.message, 'error');
    $('runStatus').textContent = e.message;
  }
}

async function fleetAction(action) {
  try {
    setStatus(`${action === 'start' ? 'Starting' : 'Stopping'} both AWS workers…`, 'working');
    await Promise.all([
      call(`/instances/x86_64/${action}`, {method:'POST'}),
      call(`/instances/arm64/${action}`, {method:'POST'})
    ]);
    const message = `${action} requested for both workers. AWS state changes can take a short time.`;
    setStatus(message, 'success');
    $('runStatus').textContent = message;
    setTimeout(refresh, 3000);
  } catch(e) {
    setStatus(e.message, 'error');
    $('runStatus').textContent = e.message;
  }
}

$('startBoth').onclick = () => fleetAction('start');
$('stopBoth').onclick = () => fleetAction('stop');
$('refresh').onclick = refresh;

document.querySelectorAll('[data-arch]').forEach(b => b.onclick = async () => {
  try {
    setStatus(`${b.dataset.action === 'start' ? 'Starting' : 'Stopping'} ${b.dataset.arch}…`, 'working');
    await call(`/instances/${b.dataset.arch}/${b.dataset.action}`, {method:'POST'});
    const message = `${b.dataset.action} requested for ${b.dataset.arch}.`;
    setStatus(message, 'success');
    $('runStatus').textContent = message;
    setTimeout(refresh, 3000);
  } catch(e) {
    setStatus(e.message, 'error');
    $('runStatus').textContent = e.message;
  }
});

function row(name, r) {
  return `<tr><td>${name}</td><td>${r.median_wall_seconds}s</td><td>${Number(r.throughput_records_per_sec).toLocaleString()} rec/s</td><td>${r.median_cpu_seconds}s</td><td>${Number(r.max_rss_kb).toLocaleString()} KB</td></tr>`;
}

async function poll(runId) {
  for (let i=0; i<120; i++) {
    try {
      const r = await call(`/benchmark/results/${runId}`);
      if (r.complete) {
        $('results').innerHTML = row('x86_64', r.x86_64) + row('ARM64 / Graviton', r.arm64);
        $('comparison').textContent = `ARM/x86 throughput ratio: ${r.comparison.arm_vs_x86_throughput_ratio}× · Faster: ${r.comparison.faster_architecture}`;
        const message = `Run ${runId} complete.`;
        setStatus(message, 'success');
        $('runStatus').textContent = message;
        return;
      }
      const message = `Run ${runId} is executing…`;
      setStatus(message, 'working');
      $('runStatus').textContent = message;
    } catch (e) {
      setStatus(e.message, 'error');
      $('runStatus').textContent = e.message;
      return;
    }
    await new Promise(resolve => setTimeout(resolve, 5000));
  }
  const message = 'Timed out waiting for results; refresh status and try the result again later.';
  setStatus(message, 'error');
  $('runStatus').textContent = message;
}

$('run').onclick = async () => {
  try {
    setStatus('Submitting benchmark to both workers…', 'working');
    const body = {
      records:Number($('records').value),
      iterations:Number($('iterations').value),
      mode:$('mode').value,
      auto_stop:$('autoStop').checked
    };
    const r = await call('/benchmark/run', {method:'POST', body:JSON.stringify(body)});
    const message = `Started ${r.run_id}`;
    setStatus(message, 'working');
    $('runStatus').textContent = message;
    poll(r.run_id);
  } catch(e) {
    setStatus(e.message, 'error');
    $('runStatus').textContent = e.message;
  }
};

if (!apiBase.value) {
  setStatus('Dashboard API URL is missing. Run the dashboard update/deploy script.', 'error');
} else if (!token.value) {
  setStatus('Enter your admin token above and click Use configuration.', 'info');
} else {
  refresh();
}
