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
  catch { /* dashboard still works without browser storage */ }
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
  return {base, t};
}

async function call(path, options={}) {
  const {base,t} = cfg();
  let response;
  try {
    response = await fetch(base + path, {
      ...options,
      headers: {'content-type':'application/json','x-admin-token':t,...(options.headers||{})}
    });
  } catch (e) {
    throw new Error(`Network/API request failed: ${e.message}`);
  }
  const text = await response.text();
  let body = {};
  if (text) {
    try { body = JSON.parse(text); }
    catch { body = {error:text}; }
  }
  if (!response.ok) throw new Error(body.error || `API returned HTTP ${response.status}`);
  return body;
}

$('saveConfig').onclick = async () => {
  storageSet('apiBase', apiBase.value.trim());
  storageSet('adminToken', token.value.trim());
  setStatus('Configuration accepted. Checking HPC and ZCU status…', 'working');
  await refresh();
};

async function refresh() {
  try {
    setStatus('Checking AWS node status…', 'working');
    const s = await call('/status');
    $('x86State').textContent = s.x86_64.state;
    $('x86Type').textContent = `${s.x86_64.instance_type} · ${s.x86_64.architecture} · ${s.x86_64.private_ip || 'no private IP'}`;
    $('armState').textContent = s.arm64.state;
    $('armType').textContent = `${s.arm64.instance_type} · ${s.arm64.architecture} · ${s.arm64.private_ip || 'no private IP'}`;
    setStatus(`Connected. ZCU: ${s.x86_64.state} · Graviton HPC: ${s.arm64.state}`, 'success');
  } catch (e) { setStatus(e.message, 'error'); }
}

async function fleetAction(action) {
  try {
    setStatus(`${action === 'start' ? 'Starting' : 'Stopping'} HPC and ZCU…`, 'working');
    await Promise.all([
      call(`/instances/x86_64/${action}`, {method:'POST'}),
      call(`/instances/arm64/${action}`, {method:'POST'})
    ]);
    setStatus(`${action} requested for HPC and ZCU.`, 'success');
    setTimeout(refresh, 3000);
  } catch(e) { setStatus(e.message, 'error'); }
}

$('startBoth').onclick = () => fleetAction('start');
$('stopBoth').onclick = () => fleetAction('stop');
$('refresh').onclick = refresh;

document.querySelectorAll('[data-arch]').forEach(button => button.onclick = async () => {
  try {
    const role = button.dataset.arch === 'arm64' ? 'Graviton HPC' : 'x86 ZCU';
    setStatus(`${button.dataset.action === 'start' ? 'Starting' : 'Stopping'} ${role}…`, 'working');
    await call(`/instances/${button.dataset.arch}/${button.dataset.action}`, {method:'POST'});
    setStatus(`${button.dataset.action} requested for ${role}.`, 'success');
    setTimeout(refresh, 3000);
  } catch(e) { setStatus(e.message, 'error'); }
});

function verdict(value) { return value ? 'PASS' : 'FAIL'; }
function fmt(value, digits=3) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  return Number(value).toFixed(digits);
}

function drawTrace(canvasId, trace, key, unit) {
  const canvas = $(canvasId);
  if (!canvas || !trace || trace.length < 2) return;
  const ctx = canvas.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const cssWidth = Math.max(320, canvas.parentElement.clientWidth - 2);
  const cssHeight = 250;
  canvas.style.width = `${cssWidth}px`;
  canvas.style.height = `${cssHeight}px`;
  canvas.width = Math.floor(cssWidth * dpr);
  canvas.height = Math.floor(cssHeight * dpr);
  ctx.scale(dpr, dpr);

  const pad = {l:62, r:18, t:18, b:42};
  const width = cssWidth - pad.l - pad.r;
  const height = cssHeight - pad.t - pad.b;
  const points = trace.filter(p => p[key] !== null && p[key] !== undefined);
  if (!points.length) return;
  const xmin = points[0].t_s;
  const xmax = points[points.length - 1].t_s;
  let ymin = Math.min(...points.map(p => Number(p[key])));
  let ymax = Math.max(...points.map(p => Number(p[key])));
  if (ymin === ymax) { ymin -= 1; ymax += 1; }
  const margin = (ymax - ymin) * 0.08;
  ymin -= margin; ymax += margin;
  const x = t => pad.l + (t - xmin) / (xmax - xmin) * width;
  const y = v => pad.t + (ymax - v) / (ymax - ymin) * height;

  ctx.clearRect(0, 0, cssWidth, cssHeight);
  ctx.strokeStyle = '#d1d5db';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(pad.l, pad.t);
  ctx.lineTo(pad.l, pad.t + height);
  ctx.lineTo(pad.l + width, pad.t + height);
  ctx.stroke();

  ctx.fillStyle = '#6b7280';
  ctx.font = '12px system-ui';
  ctx.fillText(`${fmt(ymax, 2)} ${unit}`, 4, pad.t + 4);
  ctx.fillText(`${fmt(ymin, 2)} ${unit}`, 4, pad.t + height);
  ctx.fillText(`${fmt(xmin, 1)} s`, pad.l, cssHeight - 12);
  ctx.fillText(`${fmt(xmax, 1)} s`, pad.l + width - 35, cssHeight - 12);

  ctx.strokeStyle = '#111827';
  ctx.lineWidth = 2;
  ctx.beginPath();
  points.forEach((p, i) => {
    const px = x(Number(p.t_s));
    const py = y(Number(p[key]));
    if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
  });
  ctx.stroke();
}

function renderResult(data) {
  const h = data.hpc;
  const z = data.zcu;
  const n = data.network || {};

  $('results').innerHTML = `<tr>
    <td>${h.yaw_ratio_1s_pct}% (${verdict(h.stability_1s_pass)})</td>
    <td>${h.yaw_ratio_1_75s_pct}% (${verdict(h.stability_1_75s_pass)})</td>
    <td>${h.lateral_displacement_1_07s_m} m (${verdict(h.responsiveness_pass)})</td>
    <td>${verdict(h.simulated_fmvss126_pass)}</td>
  </tr>`;

  $('comparison').textContent = `ESC: ${String(h.esc).toUpperCase()} · Graviton HPC → x86 ZCU via real UDP/IPv4 · ZCU private IP: ${h.zcu_private_ip}:${h.udp_port}`;

  $('networkResults').innerHTML = `<tr>
    <td>${n.packets_sent ?? '—'}</td>
    <td>${n.packets_received ?? '—'}</td>
    <td>${n.packet_loss_pct ?? '—'}%</td>
    <td>${fmt(n.rtt_ms_mean, 4)} ms</td>
    <td>${fmt(n.rtt_ms_p95, 4)} ms</td>
    <td>${n.deadline_misses ?? '—'}</td>
  </tr>`;

  $('zcuMetrics').textContent = `x86 ZCU controller: ${z.packets_received} UDP frames received · sequence gaps: ${z.sequence_gaps} · mean controller compute: ${fmt(z.controller_processing_us_mean, 3)} µs · P95: ${fmt(z.controller_processing_us_p95, 3)} µs.`;

  drawTrace('steeringChart', h.trace, 'steer_sw_deg', 'deg');
  drawTrace('yawChart', h.trace, 'yaw_rate_dps', 'deg/s');
  drawTrace('ayChart', h.trace, 'lateral_accel_mps2', 'm/s²');
  drawTrace('momentChart', h.trace, 'esc_yaw_moment_nm', 'Nm');
  drawTrace('rttChart', h.trace, 'network_rtt_ms', 'ms');
}

async function poll(runId) {
  for (let i=0; i<120; i++) {
    try {
      const result = await call(`/benchmark/results/${runId}`);
      if (result.complete) {
        renderResult(result);
        setStatus(`Distributed ESC SIL run ${runId} complete.`, 'success');
        return;
      }
      setStatus(`Distributed ESC SIL run ${runId} is executing…`, 'working');
    } catch (e) {
      setStatus(e.message, 'error');
      return;
    }
    await new Promise(resolve => setTimeout(resolve, 3000));
  }
  setStatus('Timed out waiting for results.', 'error');
}

$('run').onclick = async () => {
  try {
    setStatus('Starting x86 ZCU service and Graviton HPC maneuver…', 'working');
    const body = {esc:$('esc').value, auto_stop:$('autoStop').checked};
    const result = await call('/benchmark/run', {method:'POST', body:JSON.stringify(body)});
    setStatus(`Started run ${result.run_id}; real UDP ${result.zcu_private_ip}:${result.udp_port}`, 'working');
    poll(result.run_id);
  } catch(e) { setStatus(e.message, 'error'); }
};

setStatus('Dashboard JavaScript loaded. Enter/confirm the admin token and click Use configuration.', 'info');
if (apiBase.value && token.value) refresh();
