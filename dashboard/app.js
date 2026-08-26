const $ = id => document.getElementById(id);
const apiBase = $('apiBase');
const token = $('token');
const globalStatus = $('globalStatus');
const runStatus = $('runStatus');
const p2Status = $('p2Status');
const p2MeasuredRunStatus = $('p2MeasuredRunStatus');

function storageGet(key) { try { return sessionStorage.getItem(key); } catch { return null; } }
function storageSet(key, value) { try { sessionStorage.setItem(key, value); } catch {} }

apiBase.value = (window.APP_CONFIG && window.APP_CONFIG.apiBase) || storageGet('apiBase') || '';
token.value = storageGet('adminToken') || '';

function setStatus(message, type='info') {
  globalStatus.textContent = message;
  globalStatus.className = `status-banner ${type}`;
}

function cfg() {
  const base = apiBase.value.trim().replace(/\/$/, '');
  const t = token.value.trim();
  if (!base) throw new Error('API URL is missing.');
  if (!t) throw new Error('Enter the dashboard admin token and click Use configuration.');
  return {base, t};
}

async function call(path, options={}) {
  const {base, t} = cfg();
  const response = await fetch(base + path, {
    ...options,
    headers: {'content-type':'application/json','x-admin-token':t,...(options.headers||{})}
  });
  const text = await response.text();
  let body = {};
  try { body = text ? JSON.parse(text) : {}; } catch { body = {error:text}; }
  if (!response.ok) throw new Error(body.error || `API returned HTTP ${response.status}`);
  return body;
}

function showTab(id) {
  document.querySelectorAll('.lab-view').forEach(view => { view.hidden = view.id !== id; });
  document.querySelectorAll('.tab-button').forEach(button => button.classList.toggle('active', button.dataset.tab === id));
  storageSet('activeLab', id);
}
document.querySelectorAll('.tab-button').forEach(button => button.onclick = () => showTab(button.dataset.tab));
showTab(storageGet('activeLab') || 'escLab');

function showP2Mode(mode) {
  $('p2ModelView').hidden = mode !== 'model';
  $('p2MeasuredView').hidden = mode !== 'measured';
  $('p2Mode').value = mode;
  storageSet('p2Mode', mode);
  if (mode === 'measured' && apiBase.value && token.value) refreshP2Nodes();
}
$('p2Mode').onchange = () => showP2Mode($('p2Mode').value);
showP2Mode(storageGet('p2Mode') || 'measured');

$('saveConfig').onclick = async () => {
  storageSet('apiBase', apiBase.value.trim());
  storageSet('adminToken', token.value.trim());
  setStatus('Configuration accepted. Checking AWS control plane…', 'working');
  await refreshEsc();
  if ($('p2Mode').value === 'measured') await refreshP2Nodes();
};

function fmt(value, digits=3) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  return Number(value).toFixed(digits);
}
function verdict(value) { return value ? 'PASS' : 'FAIL'; }

async function refreshEsc() {
  try {
    const s = await call('/status');
    $('x86State').textContent = `${s.x86_64.state} · SSM ${s.x86_64.ssm_ping_status}`;
    $('x86Type').textContent = `${s.x86_64.instance_type} · ${s.x86_64.architecture} · ${s.x86_64.private_ip || 'no private IP'}`;
    $('armState').textContent = `${s.arm64.state} · SSM ${s.arm64.ssm_ping_status}`;
    $('armType').textContent = `${s.arm64.instance_type} · ${s.arm64.architecture} · ${s.arm64.private_ip || 'no private IP'}`;
    setStatus('Connected to AWS automotive lab.', 'success');
  } catch (e) { setStatus(e.message, 'error'); }
}

async function escFleetAction(action) {
  try {
    setStatus(`${action === 'start' ? 'Starting' : 'Stopping'} ESC HPC and ZCU…`, 'working');
    await Promise.all([
      call(`/instances/x86_64/${action}`, {method:'POST'}),
      call(`/instances/arm64/${action}`, {method:'POST'})
    ]);
    setTimeout(refreshEsc, 3000);
  } catch (e) { setStatus(e.message, 'error'); }
}
$('startBoth').onclick = () => escFleetAction('start');
$('stopBoth').onclick = () => escFleetAction('stop');
$('refresh').onclick = refreshEsc;
document.querySelectorAll('[data-arch]').forEach(button => button.onclick = async () => {
  try {
    await call(`/instances/${button.dataset.arch}/${button.dataset.action}`, {method:'POST'});
    setTimeout(refreshEsc, 3000);
  } catch (e) { setStatus(e.message, 'error'); }
});

function drawTrace(canvasId, trace, key, unit) {
  const canvas = $(canvasId);
  if (!canvas || !trace || trace.length < 2) return;
  const points = trace.filter(p => p[key] !== null && p[key] !== undefined);
  if (points.length < 2) return;
  const ctx = canvas.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const cssWidth = Math.max(320, canvas.parentElement.clientWidth - 2);
  const cssHeight = 250;
  canvas.style.width = `${cssWidth}px`; canvas.style.height = `${cssHeight}px`;
  canvas.width = Math.floor(cssWidth*dpr); canvas.height = Math.floor(cssHeight*dpr);
  ctx.setTransform(dpr,0,0,dpr,0,0);
  const pad={l:62,r:18,t:18,b:42}, width=cssWidth-pad.l-pad.r, height=cssHeight-pad.t-pad.b;
  const xmin=Number(points[0].t_s), xmax=Number(points[points.length-1].t_s);
  let ymin=Math.min(...points.map(p=>Number(p[key]))), ymax=Math.max(...points.map(p=>Number(p[key])));
  if (ymin===ymax) { ymin-=1; ymax+=1; }
  const margin=(ymax-ymin)*0.08; ymin-=margin; ymax+=margin;
  const x=t=>pad.l+(t-xmin)/(xmax-xmin)*width, y=v=>pad.t+(ymax-v)/(ymax-ymin)*height;
  ctx.clearRect(0,0,cssWidth,cssHeight); ctx.strokeStyle='#d1d5db'; ctx.beginPath();
  ctx.moveTo(pad.l,pad.t); ctx.lineTo(pad.l,pad.t+height); ctx.lineTo(pad.l+width,pad.t+height); ctx.stroke();
  ctx.fillStyle='#6b7280'; ctx.font='12px system-ui'; ctx.fillText(`${fmt(ymax,2)} ${unit}`,4,pad.t+4); ctx.fillText(`${fmt(ymin,2)} ${unit}`,4,pad.t+height);
  ctx.strokeStyle='#111827'; ctx.lineWidth=2; ctx.beginPath();
  points.forEach((p,i)=>{const px=x(Number(p.t_s)), py=y(Number(p[key])); if(i===0)ctx.moveTo(px,py);else ctx.lineTo(px,py);}); ctx.stroke();
}

function renderEsc(data) {
  const h=data.hpc, z=data.zcu, n=data.network||{};
  $('results').innerHTML=`<tr><td>${h.yaw_ratio_1s_pct}% (${verdict(h.stability_1s_pass)})</td><td>${h.yaw_ratio_1_75s_pct}% (${verdict(h.stability_1_75s_pass)})</td><td>${h.lateral_displacement_1_07s_m} m (${verdict(h.responsiveness_pass)})</td><td>${verdict(h.simulated_fmvss126_pass)}</td></tr>`;
  $('comparison').textContent=`ESC ${String(h.esc).toUpperCase()} · real UDP/IPv4 · ${h.zcu_private_ip}:${h.udp_port}`;
  $('networkResults').innerHTML=`<tr><td>${n.packets_sent??'—'}</td><td>${n.packets_received??'—'}</td><td>${n.packet_loss_pct??'—'}%</td><td>${fmt(n.rtt_ms_mean,4)} ms</td><td>${fmt(n.rtt_ms_p95,4)} ms</td><td>${n.deadline_misses??'—'}</td></tr>`;
  $('zcuMetrics').textContent=`x86 ZCU: ${z.packets_received} frames · sequence gaps ${z.sequence_gaps} · controller mean ${fmt(z.controller_processing_us_mean,3)} µs.`;
  drawTrace('steeringChart',h.trace,'steer_sw_deg','deg'); drawTrace('yawChart',h.trace,'yaw_rate_dps','deg/s'); drawTrace('ayChart',h.trace,'lateral_accel_mps2','m/s²'); drawTrace('momentChart',h.trace,'esc_yaw_moment_nm','Nm'); drawTrace('rttChart',h.trace,'network_rtt_ms','ms');
}

async function pollEsc(runId) {
  for (let i=0;i<120;i++) {
    try {
      const result=await call(`/benchmark/results/${runId}`);
      if(result.complete){renderEsc(result);runStatus.textContent=`Run ${runId} complete.`;setStatus('Distributed ESC SIL complete.','success');return;}
      runStatus.textContent=`Run ${runId} executing…`;
    } catch(e){runStatus.textContent=e.message;setStatus(e.message,'error');return;}
    await new Promise(r=>setTimeout(r,3000));
  }
  runStatus.textContent='Timed out waiting for ESC results.';
}
$('run').onclick=async()=>{try{const result=await call('/benchmark/run',{method:'POST',body:JSON.stringify({esc:$('esc').value,auto_stop:$('autoStop').checked})});runStatus.textContent=`Started ${result.run_id}`;pollEsc(result.run_id);}catch(e){runStatus.textContent=e.message;setStatus(e.message,'error');}};

function modelP2Body(){
  const body={architecture:$('p2Architecture').value,profile:$('p2Profile').value,budget_ms:Number($('p2Budget').value),samples:Number($('p2Samples').value)};
  if(body.profile==='custom') body.custom_server={mean_ms:Number($('p2Mean').value),sigma_ms:Number($('p2Sigma').value),minimum_ms:Number($('p2Min').value),maximum_ms:Number($('p2Max').value)};
  return body;
}
function measuredP2Body(){
  const body={
    architecture:$('mp2Architecture').value,profile:$('mp2Profile').value,budget_ms:Number($('mp2Budget').value),samples:Number($('mp2Samples').value),proxy_work_ms:Number($('mp2ProxyWork').value),
    can_load:Number($('mp2CanLoad').value)/100,can_arb_bps:Number($('mp2CanArb').value)*1000,can_data_bps:Number($('mp2CanData').value)*1000000,auto_stop:$('mp2AutoStop').checked
  };
  if(body.profile==='custom') body.custom_server={mean_ms:Number($('mp2Mean').value),sigma_ms:Number($('mp2Sigma').value),minimum_ms:Number($('mp2Min').value),maximum_ms:Number($('mp2Max').value)};
  return body;
}
$('p2Profile').onchange=()=>{$('p2Custom').hidden=$('p2Profile').value!=='custom';};
$('mp2Profile').onchange=()=>{$('mp2Custom').hidden=$('mp2Profile').value!=='custom';};

function drawHistogram(canvas,bins,budgetMs,label){
  const ctx=canvas.getContext('2d'),dpr=window.devicePixelRatio||1,cssWidth=Math.max(320,canvas.parentElement.clientWidth-2),cssHeight=260;
  canvas.style.width=`${cssWidth}px`;canvas.style.height=`${cssHeight}px`;canvas.width=Math.floor(cssWidth*dpr);canvas.height=Math.floor(cssHeight*dpr);ctx.setTransform(dpr,0,0,dpr,0,0);
  const pad={l:55,r:18,t:20,b:42},width=cssWidth-pad.l-pad.r,height=cssHeight-pad.t-pad.b,maxCount=Math.max(1,...bins.map(b=>b.count)),maxMs=Math.max(1,bins[bins.length-1].to_ms),barW=width/bins.length;
  ctx.clearRect(0,0,cssWidth,cssHeight);ctx.fillStyle='#111827';bins.forEach((b,i)=>{const h=b.count/maxCount*height;ctx.fillRect(pad.l+i*barW+1,pad.t+height-h,Math.max(1,barW-2),h);});
  ctx.strokeStyle='#9ca3af';ctx.beginPath();ctx.moveTo(pad.l,pad.t);ctx.lineTo(pad.l,pad.t+height);ctx.lineTo(pad.l+width,pad.t+height);ctx.stroke();
  const bx=pad.l+Math.min(1,budgetMs/maxMs)*width;ctx.strokeStyle='#b91c1c';ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(bx,pad.t);ctx.lineTo(bx,pad.t+height);ctx.stroke();ctx.fillStyle='#374151';ctx.font='12px system-ui';ctx.fillText(label,pad.l,14);
}

function renderResultTable(results,tableId){
  $(tableId).innerHTML=results.map(r=>`<tr><td>${r.label}</td><td>${fmt(r.p2tester_elapsed_ms.mean)} ms</td><td>${fmt(r.p2tester_elapsed_ms.p50)} ms</td><td>${fmt(r.p2tester_elapsed_ms.p95)} ms</td><td>${fmt(r.p2tester_elapsed_ms.p99)} ms</td><td>${fmt(r.p2tester_elapsed_ms.max)} ms</td><td>${fmt(r.budget_miss_pct)}%</td><td>${r.meets_99_percent?'PASS':'FAIL'}</td></tr>`).join('');
}
function renderHistograms(results,containerId,prefix){
  const container=$(containerId);container.innerHTML='';results.forEach((r,i)=>{const card=document.createElement('div');card.className='chart-card';const h=document.createElement('h3');h.textContent=r.label;const c=document.createElement('canvas');c.id=`${prefix}${i}`;card.appendChild(h);card.appendChild(c);container.appendChild(card);drawHistogram(c,r.histogram,r.p2tester_budget_ms,r.label);});
}
function conclusion(results,id,prefix=''){
  if(!results.length)return;const fastest=[...results].sort((a,b)=>a.p2tester_elapsed_ms.p99-b.p2tester_elapsed_ms.p99)[0];const riskiest=[...results].sort((a,b)=>b.budget_miss_pct-a.budget_miss_pct)[0];$(id).textContent=`${prefix}Lowest P99: ${fastest.label} ${fmt(fastest.p2tester_elapsed_ms.p99)} ms. Highest budget-miss rate: ${riskiest.label} ${fmt(riskiest.budget_miss_pct)}%.`;
}
function renderModelBreakdown(results){
  $('p2Breakdown').innerHTML=results.map(r=>{const components=Object.entries(r.architecture_delay_ms.mean_components||{}).map(([n,v])=>`<li><span>${n.replaceAll('_',' ')}</span><strong>${fmt(v)} ms</strong></li>`).join('');return `<article class="breakdown-card"><h3>${r.label}</h3><ul><li><span>Server processing</span><strong>${fmt(r.server_processing_ms.mean)} ms</strong></li>${components}<li class="total"><span>P2Tester mean</span><strong>${fmt(r.p2tester_elapsed_ms.mean)} ms</strong></li></ul></article>`;}).join('');
}
function renderModel(data){const results=data.results||[];renderResultTable(results,'p2Results');renderModelBreakdown(results);renderHistograms(results,'p2Histograms','modelHist');conclusion(results,'p2Conclusion','Modeled — ');}
$('runP2').onclick=async()=>{try{p2Status.textContent='Running Lambda timing model…';const result=await call('/p2/simulate',{method:'POST',body:JSON.stringify(modelP2Body())});renderModel(result);p2Status.textContent='Modeled study complete.';}catch(e){p2Status.textContent=e.message;setStatus(e.message,'error');}};

function nodeLine(node){return `${node.state} · SSM ${node.ssm_ping_status}`;}
function nodeType(node){return `${node.instance_type} · ${node.architecture} · ${node.private_ip||'no private IP'}`;}
function fleetSummary(nodes,keys){
  const fleet=keys.map(k=>nodes[k]).filter(Boolean);const running=fleet.filter(n=>n.state==='running').length,online=fleet.filter(n=>n.ssm_ping_status==='Online').length;const types=[...new Set(fleet.map(n=>`${n.instance_type}/${n.architecture}`))].join(', ');return {state:`${running}/${fleet.length} running · ${online}/${fleet.length} SSM Online`,type:types||'—'};
}
async function refreshP2Nodes(){
  try{
    const nodes=await call('/p2/measured/status');
    $('p2TesterState').textContent=nodeLine(nodes.tester);$('p2TesterType').textContent=nodeType(nodes.tester);
    $('p2LegacyGatewayState').textContent=nodeLine(nodes.legacy_gateway);$('p2LegacyGatewayType').textContent=nodeType(nodes.legacy_gateway);
    $('p2HpcState').textContent=nodeLine(nodes.hpc);$('p2HpcType').textContent=nodeType(nodes.hpc);
    const legacy=fleetSummary(nodes,['legacy_ecu1','legacy_ecu2','legacy_ecu3','legacy_ecu4']);$('p2LegacyEcuState').textContent=legacy.state;$('p2LegacyEcuType').textContent=legacy.type;
    const zcus=fleetSummary(nodes,['zcu1','zcu2','zcu3','zcu4']);$('p2ZcuState').textContent=zcus.state;$('p2ZcuType').textContent=zcus.type;
    const ready=Object.values(nodes).every(n=>n.state==='running'&&n.ssm_ping_status==='Online');
    p2MeasuredRunStatus.textContent=ready?'All 11 benchmark nodes are running and SSM Online. Ready.':'Benchmark nodes are not all ready yet.';
    setStatus(ready?'11-node architecture benchmark is ready.':'Connected; benchmark fleet not fully ready.','info');
  }catch(e){p2MeasuredRunStatus.textContent=e.message;setStatus(e.message,'error');}
}
async function p2FleetAction(action){try{setStatus(`${action==='start'?'Starting':'Stopping'} 11 benchmark nodes…`,'working');await call(`/p2/measured/nodes/${action}`,{method:'POST'});p2MeasuredRunStatus.textContent=`${action} requested for all 11 nodes.`;setTimeout(refreshP2Nodes,4000);}catch(e){p2MeasuredRunStatus.textContent=e.message;setStatus(e.message,'error');}}
$('startP2Nodes').onclick=()=>p2FleetAction('start');$('stopP2Nodes').onclick=()=>p2FleetAction('stop');$('refreshP2Nodes').onclick=refreshP2Nodes;

function renderPerServer(results){
  $('p2MeasuredPerServer').innerHTML=results.map(r=>{const rows=Object.entries(r.per_server_p2tester_ms||{}).map(([idx,s])=>`<li><span>${r.architecture==='distributed_canfd'?'ECU':'ZCU'} ${idx} P99</span><strong>${fmt(s.p99)} ms</strong></li>`).join('');return `<article class="breakdown-card"><h3>${r.label}</h3><ul>${rows}</ul></article>`;}).join('');
}
function renderMeasured(data){const results=data.results||[];renderResultTable(results,'p2MeasuredResults');renderPerServer(results);renderHistograms(results,'p2MeasuredHistograms','measuredHist');conclusion(results,'p2MeasuredConclusion','Measured — ');}
function commandFailureText(envelope){if(!envelope.failed_commands)return envelope.error||'Benchmark failed.';return Object.entries(envelope.failed_commands).map(([r,s])=>`${r}: ${s.status}${s.stderr?` — ${s.stderr}`:''}`).join(' | ');}
async function pollP2Measured(runId){
  for(let i=0;i<500;i++){
    try{const envelope=await call(`/p2/measured/results/${runId}`);if(envelope.complete&&envelope.result){renderMeasured(envelope.result);p2MeasuredRunStatus.textContent=`Measured run ${runId} complete.`;setStatus('Measured architecture benchmark complete.','success');if($('mp2AutoStop').checked)setTimeout(refreshP2Nodes,5000);return;}if(envelope.error)throw new Error(commandFailureText(envelope));const status=Object.entries(envelope.commands||{}).map(([r,s])=>`${r}:${s.status}`).join(' · ');p2MeasuredRunStatus.textContent=`Run ${runId} executing… ${status}`;}catch(e){p2MeasuredRunStatus.textContent=e.message;setStatus(e.message,'error');return;}await new Promise(r=>setTimeout(r,3000));
  }
  p2MeasuredRunStatus.textContent='Timed out waiting for measured results.';
}
$('runP2Measured').onclick=async()=>{try{p2MeasuredRunStatus.textContent='Launching 4 ECUs + gateway + Graviton HPC + 4 ZCUs + tester…';setStatus('Starting measured architecture benchmark…','working');const result=await call('/p2/measured/run',{method:'POST',body:JSON.stringify(measuredP2Body())});p2MeasuredRunStatus.textContent=`Run ${result.run_id} started on DoIP TCP/${result.port}.`;pollP2Measured(result.run_id);}catch(e){p2MeasuredRunStatus.textContent=e.message;setStatus(e.message,'error');}};

setStatus('Dashboard loaded. Enter/confirm the admin token and click Use configuration.','info');
if(apiBase.value&&token.value){refreshEsc();if($('p2Mode').value==='measured')refreshP2Nodes();}
