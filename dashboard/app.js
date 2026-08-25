const $ = id => document.getElementById(id);
const apiBase = $('apiBase');
const token = $('token');
const globalStatus = $('globalStatus');
const runStatus = $('runStatus');
const p2Status = $('p2Status');
const p2MeasuredRunStatus = $('p2MeasuredRunStatus');

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

function showTab(id) {
  document.querySelectorAll('.lab-view').forEach(view => { view.hidden = view.id !== id; });
  document.querySelectorAll('.tab-button').forEach(button => button.classList.toggle('active', button.dataset.tab === id));
  storageSet('activeLab', id);
}

document.querySelectorAll('.tab-button').forEach(button => {
  button.onclick = () => showTab(button.dataset.tab);
});
showTab(storageGet('activeLab') || 'escLab');

function showP2Mode(mode) {
  $('p2ModelView').hidden = mode !== 'model';
  $('p2MeasuredView').hidden = mode !== 'measured';
  $('p2Mode').value = mode;
  storageSet('p2Mode', mode);
  if (mode === 'measured' && apiBase.value && token.value) refreshP2Nodes();
}
$('p2Mode').onchange = () => showP2Mode($('p2Mode').value);
showP2Mode(storageGet('p2Mode') || 'model');

$('saveConfig').onclick = async () => {
  storageSet('apiBase', apiBase.value.trim());
  storageSet('adminToken', token.value.trim());
  setStatus('Configuration accepted. Checking AWS control plane…', 'working');
  await refresh();
  if ($('p2Mode').value === 'measured') await refreshP2Nodes();
};

async function refresh() {
  try {
    setStatus('Checking ESC AWS node and Systems Manager status…', 'working');
    const s = await call('/status');
    $('x86State').textContent = `${s.x86_64.state} · SSM ${s.x86_64.ssm_ping_status}`;
    $('x86Type').textContent = `${s.x86_64.instance_type} · ${s.x86_64.architecture} · ${s.x86_64.private_ip || 'no private IP'}`;
    $('armState').textContent = `${s.arm64.state} · SSM ${s.arm64.ssm_ping_status}`;
    $('armType').textContent = `${s.arm64.instance_type} · ${s.arm64.architecture} · ${s.arm64.private_ip || 'no private IP'}`;

    const ready = s.x86_64.state === 'running' && s.arm64.state === 'running' &&
      s.x86_64.ssm_ping_status === 'Online' && s.arm64.ssm_ping_status === 'Online';
    if (ready) {
      setStatus('Connected. ESC HPC and ZCU are SSM Online.', 'success');
    } else {
      setStatus(`Connected. ESC nodes: ZCU ${s.x86_64.state}/SSM ${s.x86_64.ssm_ping_status} · HPC ${s.arm64.state}/SSM ${s.arm64.ssm_ping_status}.`, 'info');
    }
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
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

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
    <td>${n.packets_sent ?? '—'}</td><td>${n.packets_received ?? '—'}</td><td>${n.packet_loss_pct ?? '—'}%</td>
    <td>${fmt(n.rtt_ms_mean, 4)} ms</td><td>${fmt(n.rtt_ms_p95, 4)} ms</td><td>${n.deadline_misses ?? '—'}</td>
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
        if (runStatus) runStatus.textContent = `Distributed ESC SIL run ${runId} complete.`;
        setStatus(`Distributed ESC SIL run ${runId} complete.`, 'success');
        return;
      }
      if (runStatus) runStatus.textContent = `Run ${runId} is executing…`;
    } catch (e) {
      if (runStatus) runStatus.textContent = e.message;
      setStatus(e.message, 'error');
      return;
    }
    await new Promise(resolve => setTimeout(resolve, 3000));
  }
  if (runStatus) runStatus.textContent = 'Timed out waiting for ESC results.';
  setStatus('Timed out waiting for ESC results.', 'error');
}

$('run').onclick = async () => {
  try {
    if (runStatus) runStatus.textContent = 'Starting x86 ZCU service and Graviton HPC maneuver…';
    setStatus('Starting x86 ZCU service and Graviton HPC maneuver…', 'working');
    const body = {esc:$('esc').value, auto_stop:$('autoStop').checked};
    const result = await call('/benchmark/run', {method:'POST', body:JSON.stringify(body)});
    if (runStatus) runStatus.textContent = `Started run ${result.run_id}; real UDP ${result.zcu_private_ip}:${result.udp_port}`;
    poll(result.run_id);
  } catch(e) {
    if (runStatus) runStatus.textContent = e.message;
    setStatus(e.message, 'error');
  }
};

function modelP2Body() {
  const body = {
    architecture: $('p2Architecture').value,
    profile: $('p2Profile').value,
    budget_ms: Number($('p2Budget').value),
    samples: Number($('p2Samples').value)
  };
  if (body.profile === 'custom') {
    body.custom_server = {
      mean_ms: Number($('p2Mean').value), sigma_ms: Number($('p2Sigma').value),
      minimum_ms: Number($('p2Min').value), maximum_ms: Number($('p2Max').value)
    };
  }
  return body;
}

function measuredP2Body() {
  const body = {
    architecture: $('mp2Architecture').value,
    profile: $('mp2Profile').value,
    budget_ms: Number($('mp2Budget').value),
    samples: Number($('mp2Samples').value),
    proxy_work_ms: Number($('mp2ProxyWork').value),
    auto_stop: $('mp2AutoStop').checked
  };
  if (body.profile === 'custom') {
    body.custom_server = {
      mean_ms: Number($('mp2Mean').value), sigma_ms: Number($('mp2Sigma').value),
      minimum_ms: Number($('mp2Min').value), maximum_ms: Number($('mp2Max').value)
    };
  }
  return body;
}

$('p2Profile').onchange = () => { $('p2Custom').hidden = $('p2Profile').value !== 'custom'; };
$('mp2Profile').onchange = () => { $('mp2Custom').hidden = $('mp2Profile').value !== 'custom'; };

function renderBreakdown(results, elementId) {
  $(elementId).innerHTML = results.map(result => {
    const components = Object.entries(result.architecture_delay_ms.mean_components || {})
      .map(([name, value]) => `<li><span>${name.replaceAll('_', ' ')}</span><strong>${fmt(value, 3)} ms</strong></li>`).join('');
    return `<article class="breakdown-card">
      <h3>${result.label}</h3>
      <ul>
        <li><span>Target ECU processing</span><strong>${fmt(result.server_processing_ms.mean, 3)} ms</strong></li>
        ${components}
        <li class="total"><span>Total P2Tester mean</span><strong>${fmt(result.p2tester_elapsed_ms.mean, 3)} ms</strong></li>
      </ul>
    </article>`;
  }).join('');
}

function drawHistogram(canvas, bins, budgetMs, label) {
  const ctx = canvas.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const cssWidth = Math.max(320, canvas.parentElement.clientWidth - 2);
  const cssHeight = 260;
  canvas.style.width = `${cssWidth}px`;
  canvas.style.height = `${cssHeight}px`;
  canvas.width = Math.floor(cssWidth * dpr);
  canvas.height = Math.floor(cssHeight * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const pad = {l:55, r:18, t:20, b:42};
  const width = cssWidth - pad.l - pad.r;
  const height = cssHeight - pad.t - pad.b;
  const maxCount = Math.max(1, ...bins.map(bin => bin.count));
  const maxMs = Math.max(1, bins[bins.length - 1].to_ms);
  const barW = width / bins.length;

  ctx.clearRect(0, 0, cssWidth, cssHeight);
  ctx.fillStyle = '#111827';
  bins.forEach((bin, i) => {
    const h = (bin.count / maxCount) * height;
    ctx.fillRect(pad.l + i * barW + 1, pad.t + height - h, Math.max(1, barW - 2), h);
  });
  ctx.strokeStyle = '#9ca3af';
  ctx.beginPath();
  ctx.moveTo(pad.l, pad.t); ctx.lineTo(pad.l, pad.t + height); ctx.lineTo(pad.l + width, pad.t + height); ctx.stroke();
  const budgetX = pad.l + Math.min(1, budgetMs / maxMs) * width;
  ctx.strokeStyle = '#b91c1c'; ctx.lineWidth = 2; ctx.beginPath();
  ctx.moveTo(budgetX, pad.t); ctx.lineTo(budgetX, pad.t + height); ctx.stroke();
  ctx.fillStyle = '#6b7280'; ctx.font = '12px system-ui';
  ctx.fillText('0 ms', pad.l, cssHeight - 12); ctx.fillText(`${fmt(maxMs, 0)} ms`, pad.l + width - 42, cssHeight - 12);
  ctx.fillStyle = '#b91c1c'; ctx.fillText(`Budget ${fmt(budgetMs, 0)} ms`, Math.min(cssWidth - 120, budgetX + 5), pad.t + 14);
  ctx.fillStyle = '#374151'; ctx.fillText(label, pad.l, 14);
}

function renderStudy(data, ids) {
  const results = data.results || [];
  $(ids.table).innerHTML = results.map(result => `<tr>
    <td>${result.label}</td><td>${fmt(result.p2tester_elapsed_ms.mean, 3)} ms</td>
    <td>${fmt(result.p2tester_elapsed_ms.p50, 3)} ms</td><td>${fmt(result.p2tester_elapsed_ms.p95, 3)} ms</td>
    <td>${fmt(result.p2tester_elapsed_ms.p99, 3)} ms</td><td>${fmt(result.p2tester_elapsed_ms.max, 3)} ms</td>
    <td>${fmt(result.budget_miss_pct, 3)}%</td><td>${result.meets_99_percent ? 'PASS' : 'FAIL'}</td>
  </tr>`).join('');
  renderBreakdown(results, ids.breakdown);

  const hist = $(ids.histograms);
  hist.innerHTML = '';
  results.forEach((result, index) => {
    const card = document.createElement('div'); card.className = 'chart-card';
    const heading = document.createElement('h3'); heading.textContent = result.label;
    const canvas = document.createElement('canvas'); canvas.id = `${ids.canvasPrefix}${index}`;
    card.appendChild(heading); card.appendChild(canvas); hist.appendChild(card);
    drawHistogram(canvas, result.histogram, result.p2tester_budget_ms, result.label);
  });

  if (results.length > 1) {
    const fastest = [...results].sort((a,b) => a.p2tester_elapsed_ms.p99 - b.p2tester_elapsed_ms.p99)[0];
    const riskiest = [...results].sort((a,b) => b.budget_miss_pct - a.budget_miss_pct)[0];
    $(ids.conclusion).textContent = `Lowest P99: ${fastest.label} at ${fmt(fastest.p2tester_elapsed_ms.p99, 3)} ms. Highest budget-miss rate: ${riskiest.label} at ${fmt(riskiest.budget_miss_pct, 3)}%.`;
  } else if (results.length === 1) {
    const result = results[0];
    $(ids.conclusion).textContent = `${result.label}: P99 ${fmt(result.p2tester_elapsed_ms.p99, 3)} ms; ${fmt(result.budget_miss_pct, 3)}% exceed the selected budget.`;
  }
}

const MODEL_RENDER_IDS = {
  table:'p2Results', breakdown:'p2Breakdown', histograms:'p2Histograms', conclusion:'p2Conclusion', canvasPrefix:'p2Histogram'
};
const MEASURED_RENDER_IDS = {
  table:'p2MeasuredResults', breakdown:'p2MeasuredBreakdown', histograms:'p2MeasuredHistograms', conclusion:'p2MeasuredConclusion', canvasPrefix:'p2MeasuredHistogram'
};

$('runP2').onclick = async () => {
  try {
    p2Status.textContent = 'Running timing model in AWS Lambda…';
    setStatus('Running modeled OBDonUDS P2Tester architecture study…', 'working');
    const result = await call('/p2/simulate', {method:'POST', body:JSON.stringify(modelP2Body())});
    renderStudy(result, MODEL_RENDER_IDS);
    p2Status.textContent = `Complete: ${result.results.reduce((sum, item) => sum + item.samples, 0).toLocaleString()} modeled requests evaluated.`;
    setStatus('Modeled P2Tester timing study complete.', 'success');
  } catch (e) {
    p2Status.textContent = e.message; setStatus(e.message, 'error');
  }
};

function renderP2Node(role, node) {
  const prefix = {tester:'p2Tester', hpc:'p2Hpc', zone:'p2Zone', target:'p2Target'}[role];
  $(`${prefix}State`).textContent = `${node.state} · SSM ${node.ssm_ping_status}`;
  $(`${prefix}Type`).textContent = `${node.instance_type} · ${node.architecture} · ${node.private_ip || 'no private IP'}`;
}

async function refreshP2Nodes() {
  try {
    const nodes = await call('/p2/measured/status');
    Object.entries(nodes).forEach(([role,node]) => renderP2Node(role,node));
    const ready = Object.values(nodes).every(node => node.state === 'running' && node.ssm_ping_status === 'Online');
    if (ready) {
      p2MeasuredRunStatus.textContent = 'All four P2 nodes are running and SSM Online. Ready for measured test.';
      setStatus('Measured P2 lab is ready: Tester, HPC, Zone, and Target are SSM Online.', 'success');
    } else {
      const compact = Object.entries(nodes).map(([role,node]) => `${role} ${node.state}/SSM ${node.ssm_ping_status}`).join(' · ');
      p2MeasuredRunStatus.textContent = `Not ready yet: ${compact}`;
      setStatus(`Measured P2 nodes: ${compact}`, 'info');
    }
  } catch (e) {
    p2MeasuredRunStatus.textContent = e.message; setStatus(e.message, 'error');
  }
}

async function p2FleetAction(action) {
  try {
    setStatus(`${action === 'start' ? 'Starting' : 'Stopping'} the four measured P2 nodes…`, 'working');
    await call(`/p2/measured/nodes/${action}`, {method:'POST'});
    p2MeasuredRunStatus.textContent = `${action} requested for Tester, HPC, Zone, and Target.`;
    setTimeout(refreshP2Nodes, 3500);
  } catch (e) {
    p2MeasuredRunStatus.textContent = e.message; setStatus(e.message, 'error');
  }
}
$('startP2Nodes').onclick = () => p2FleetAction('start');
$('stopP2Nodes').onclick = () => p2FleetAction('stop');
$('refreshP2Nodes').onclick = refreshP2Nodes;

function commandFailureText(envelope) {
  if (!envelope.failed_commands) return envelope.error || 'Measured P2 run failed.';
  const details = Object.entries(envelope.failed_commands).map(([role, snap]) => {
    const stderr = (snap.stderr || '').trim();
    return `${role}: ${snap.status}${stderr ? ` — ${stderr}` : ''}`;
  }).join(' | ');
  return `${envelope.error || 'Measured P2 run failed.'} ${details}`;
}

async function pollP2Measured(runId) {
  for (let i=0; i<400; i++) {
    try {
      const envelope = await call(`/p2/measured/results/${runId}`);
      if (envelope.complete && envelope.result) {
        renderStudy(envelope.result, MEASURED_RENDER_IDS);
        p2MeasuredRunStatus.textContent = `Measured run ${runId} complete. Results came from the Tester EC2 end-to-end clock.`;
        setStatus('Measured AWS P2Tester test complete.', 'success');
        if ($('mp2AutoStop').checked) setTimeout(refreshP2Nodes, 3500);
        return;
      }
      if (envelope.error) throw new Error(commandFailureText(envelope));
      const commandText = Object.entries(envelope.commands || {}).map(([role,s]) => `${role}:${s.status}`).join(' · ');
      p2MeasuredRunStatus.textContent = `Measured run ${runId} executing… ${commandText}`;
    } catch (e) {
      p2MeasuredRunStatus.textContent = e.message; setStatus(e.message, 'error'); return;
    }
    await new Promise(resolve => setTimeout(resolve, 3000));
  }
  p2MeasuredRunStatus.textContent = 'Timed out waiting for measured P2 results.';
  setStatus('Timed out waiting for measured P2 results.', 'error');
}

$('runP2Measured').onclick = async () => {
  try {
    p2MeasuredRunStatus.textContent = 'Launching Target → Zone → HPC → Tester through AWS Systems Manager…';
    setStatus('Starting real multi-node P2Tester measurement…', 'working');
    const result = await call('/p2/measured/run', {method:'POST', body:JSON.stringify(measuredP2Body())});
    p2MeasuredRunStatus.textContent = `Run ${result.run_id} started on real VPC TCP/${result.port}.`;
    pollP2Measured(result.run_id);
  } catch (e) {
    p2MeasuredRunStatus.textContent = e.message; setStatus(e.message, 'error');
  }
};

setStatus('Dashboard JavaScript loaded. Enter/confirm the admin token and click Use configuration.', 'info');
if (apiBase.value && token.value) {
  refresh();
  if ($('p2Mode').value === 'measured') refreshP2Nodes();
}
