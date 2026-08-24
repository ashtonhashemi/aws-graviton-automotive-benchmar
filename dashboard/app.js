const $ = id => document.getElementById(id);
const apiBase = $('apiBase');
const token = $('token');
apiBase.value = window.APP_CONFIG?.apiBase || sessionStorage.getItem('apiBase') || '';
token.value = sessionStorage.getItem('adminToken') || '';

function cfg() {
  const base = apiBase.value.trim().replace(/\/$/, '');
  const t = token.value.trim();
  if (!base || !t) throw new Error('Enter API URL and admin token.');
  return { base, t };
}
async function call(path, options={}) {
  const {base,t} = cfg();
  const r = await fetch(base + path, { ...options, headers: { 'content-type':'application/json','x-admin-token':t, ...(options.headers||{}) }});
  const body = await r.json();
  if (!r.ok) throw new Error(body.error || `HTTP ${r.status}`);
  return body;
}
$('saveConfig').onclick = () => {
  sessionStorage.setItem('apiBase', apiBase.value.trim());
  sessionStorage.setItem('adminToken', token.value.trim());
  refresh();
};

async function refresh() {
  try {
    const s = await call('/status');
    $('x86State').textContent = s.x86_64.state;
    $('x86Type').textContent = `${s.x86_64.instance_type} · ${s.x86_64.architecture}`;
    $('armState').textContent = s.arm64.state;
    $('armType').textContent = `${s.arm64.instance_type} · ${s.arm64.architecture}`;
  } catch (e) { $('runStatus').textContent = e.message; }
}

async function fleetAction(action) {
  try {
    await Promise.all([
      call(`/instances/x86_64/${action}`, {method:'POST'}),
      call(`/instances/arm64/${action}`, {method:'POST'})
    ]);
    $('runStatus').textContent = `${action} requested for both workers.`;
    setTimeout(refresh, 2500);
  } catch(e) { $('runStatus').textContent = e.message; }
}
$('startBoth').onclick = () => fleetAction('start');
$('stopBoth').onclick = () => fleetAction('stop');
$('refresh').onclick = refresh;

document.querySelectorAll('[data-arch]').forEach(b => b.onclick = async () => {
  try {
    await call(`/instances/${b.dataset.arch}/${b.dataset.action}`, {method:'POST'});
    $('runStatus').textContent = `${b.dataset.action} requested for ${b.dataset.arch}.`;
    setTimeout(refresh, 2500);
  } catch(e) { $('runStatus').textContent = e.message; }
});

function row(name, r) {
  return `<tr><td>${name}</td><td>${r.median_wall_seconds}s</td><td>${Number(r.throughput_records_per_sec).toLocaleString()} rec/s</td><td>${r.median_cpu_seconds}s</td><td>${Number(r.max_rss_kb).toLocaleString()} KB</td></tr>`;
}
async function poll(runId) {
  for (let i=0; i<120; i++) {
    const r = await call(`/benchmark/results/${runId}`);
    if (r.complete) {
      $('results').innerHTML = row('x86_64', r.x86_64) + row('ARM64 / Graviton', r.arm64);
      $('comparison').textContent = `ARM/x86 throughput ratio: ${r.comparison.arm_vs_x86_throughput_ratio}× · Faster: ${r.comparison.faster_architecture}`;
      $('runStatus').textContent = `Run ${runId} complete.`;
      return;
    }
    $('runStatus').textContent = `Run ${runId} is executing…`;
    await new Promise(resolve => setTimeout(resolve, 5000));
  }
  $('runStatus').textContent = 'Timed out waiting for results; query the run again later.';
}
$('run').onclick = async () => {
  try {
    const body = {records:Number($('records').value), iterations:Number($('iterations').value), mode:$('mode').value, auto_stop:$('autoStop').checked};
    const r = await call('/benchmark/run', {method:'POST', body:JSON.stringify(body)});
    $('runStatus').textContent = `Started ${r.run_id}`;
    poll(r.run_id);
  } catch(e) { $('runStatus').textContent = e.message; }
};

if (apiBase.value && token.value) refresh();
