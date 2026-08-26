(() => {
  const $ = id => document.getElementById(id);
  const measuredView = $('p2MeasuredView');
  if (!measuredView) return;

  measuredView.querySelector('.measured-note')?.remove();
  const intro = document.querySelector('#p2Lab .lab-intro');
  if (intro) {
    intro.innerHTML = `
      <p class="eyebrow">Measured AWS benchmark</p>
      <h2>Legacy Distributed vs Zonal HPC Application Proxy</h2>
      <p>Compare tester-observed P2 timing across the same four diagnostic responders.</p>`;
  }

  const paths = measuredView.querySelector('.architecture-paths');
  if (paths) {
    paths.className = 'panel benchmark-architecture';
    paths.innerHTML = `
      <div class="section-heading">
        <div><p class="eyebrow">01 · Architecture</p><h2>Vehicle Networks Under Test</h2></div>
        <span class="test-badge">DoIP · SAE J1979-2 service traffic</span>
      </div>
      <div class="architecture-grid">
        <article class="architecture-card legacy-card">
          <div class="architecture-card-title">Distributed / Legacy</div>
          <svg class="architecture-svg" viewBox="0 0 620 310" role="img" aria-label="Legacy distributed architecture: tester to central gateway to three CAN-FD buses and four ECUs">
            <rect class="svg-node" x="20" y="120" width="105" height="62" rx="8"/><text class="svg-label" x="72" y="145">External OBD</text><text class="svg-label" x="72" y="163">Tester</text>
            <line class="svg-doip" x1="125" y1="151" x2="185" y2="151"/><text class="svg-edge-label" x="155" y="136">DoIP / J1979-2</text>
            <rect class="svg-node svg-gateway" x="185" y="108" width="120" height="86" rx="8"/><text class="svg-label" x="245" y="142">Central</text><text class="svg-label" x="245" y="161">Gateway</text>
            <line class="svg-can" x1="305" y1="151" x2="350" y2="151"/><line class="svg-can" x1="350" y1="58" x2="350" y2="250"/>
            <rect class="svg-bus" x="365" y="43" width="76" height="34" rx="6"/><text class="svg-bus-label" x="403" y="64">Bus A</text><line class="svg-can" x1="350" y1="60" x2="365" y2="60"/><line class="svg-can" x1="441" y1="60" x2="470" y2="60"/><line class="svg-can" x1="455" y1="60" x2="455" y2="112"/><line class="svg-can" x1="455" y1="112" x2="470" y2="112"/>
            <rect class="svg-node svg-ecu" x="470" y="35" width="105" height="50" rx="7"/><text class="svg-label" x="522" y="65">ECU 1</text><rect class="svg-node svg-ecu" x="470" y="87" width="105" height="50" rx="7"/><text class="svg-label" x="522" y="117">ECU 2</text>
            <rect class="svg-bus" x="365" y="157" width="76" height="34" rx="6"/><text class="svg-bus-label" x="403" y="178">Bus B</text><line class="svg-can" x1="350" y1="174" x2="365" y2="174"/><line class="svg-can" x1="441" y1="174" x2="470" y2="174"/><rect class="svg-node svg-ecu" x="470" y="149" width="105" height="50" rx="7"/><text class="svg-label" x="522" y="179">ECU 3</text>
            <rect class="svg-bus" x="365" y="233" width="76" height="34" rx="6"/><text class="svg-bus-label" x="403" y="254">Bus C</text><line class="svg-can" x1="350" y1="250" x2="365" y2="250"/><line class="svg-can" x1="441" y1="250" x2="470" y2="250"/><rect class="svg-node svg-ecu" x="470" y="225" width="105" height="50" rx="7"/><text class="svg-label" x="522" y="255">ECU 4</text>
            <text class="svg-network-note" x="350" y="295">CAN-FD</text>
          </svg>
        </article>
        <article class="architecture-card zonal-card">
          <div class="architecture-card-title">Zonal / HPC Application Proxy</div>
          <svg class="architecture-svg" viewBox="0 0 620 310" role="img" aria-label="Zonal architecture: tester to Graviton HPC application proxy to four ZCUs over automotive Ethernet">
            <rect class="svg-node" x="20" y="120" width="105" height="62" rx="8"/><text class="svg-label" x="72" y="145">External OBD</text><text class="svg-label" x="72" y="163">Tester</text>
            <line class="svg-doip svg-doip-zonal" x1="125" y1="151" x2="188" y2="151"/><text class="svg-edge-label" x="156" y="136">DoIP / J1979-2</text>
            <rect class="svg-node svg-hpc" x="188" y="94" width="150" height="114" rx="9"/><text class="svg-label svg-hpc-label" x="263" y="130">Graviton HPC</text><text class="svg-label" x="263" y="153">Application Proxy</text><text class="svg-sub-label" x="263" y="178">terminate · process · reissue</text>
            <line class="svg-eth" x1="338" y1="151" x2="382" y2="151"/><line class="svg-eth" x1="382" y1="50" x2="382" y2="258"/>
            <line class="svg-eth" x1="382" y1="50" x2="470" y2="50"/><line class="svg-eth" x1="382" y1="118" x2="470" y2="118"/><line class="svg-eth" x1="382" y1="190" x2="470" y2="190"/><line class="svg-eth" x1="382" y1="258" x2="470" y2="258"/>
            <rect class="svg-node svg-zcu" x="470" y="25" width="105" height="50" rx="7"/><text class="svg-label" x="522" y="55">ZCU 1</text><rect class="svg-node svg-zcu" x="470" y="93" width="105" height="50" rx="7"/><text class="svg-label" x="522" y="123">ZCU 2</text><rect class="svg-node svg-zcu" x="470" y="165" width="105" height="50" rx="7"/><text class="svg-label" x="522" y="195">ZCU 3</text><rect class="svg-node svg-zcu" x="470" y="233" width="105" height="50" rx="7"/><text class="svg-label" x="522" y="263">ZCU 4</text>
            <text class="svg-network-note" x="382" y="295">Automotive Ethernet</text>
          </svg>
        </article>
      </div>`;
  }

  const nodeGrid = measuredView.querySelector('.p2-node-grid');
  const fleetActions = measuredView.querySelector('.fleet-actions');
  if (nodeGrid) {
    nodeGrid.className = 'panel fleet-panel';
    nodeGrid.innerHTML = `<div class="section-heading"><div><p class="eyebrow">02 · Fleet</p><h2>EC2 Benchmark Nodes</h2></div><div id="benchmarkFleetActions"></div></div><div class="table-wrap"><table class="fleet-table"><thead><tr><th>Role</th><th>Status</th><th>Instance</th></tr></thead><tbody><tr><td>Tester</td><td id="p2TesterState">Unknown</td><td id="p2TesterType">—</td></tr><tr><td>Legacy gateway</td><td id="p2LegacyGatewayState">Unknown</td><td id="p2LegacyGatewayType">—</td></tr><tr><td>4 × Legacy ECU</td><td id="p2LegacyEcuState">Unknown</td><td id="p2LegacyEcuType">—</td></tr><tr><td>Graviton HPC</td><td id="p2HpcState">Unknown</td><td id="p2HpcType">—</td></tr><tr><td>4 × ZCU</td><td id="p2ZcuState">Unknown</td><td id="p2ZcuType">—</td></tr></tbody></table></div>`;
    const slot = $('benchmarkFleetActions');
    if (fleetActions && slot) { fleetActions.classList.remove('panel'); fleetActions.classList.add('compact-actions'); slot.replaceWith(fleetActions); }
  }

  const oldConfig = $('mp2Architecture')?.closest('section');
  if (!oldConfig) return;
  oldConfig.className = 'panel benchmark-settings';
  oldConfig.innerHTML = `<div class="section-heading"><div><p class="eyebrow">03 · Configure</p><h2>Benchmark Settings</h2></div><span class="settings-count">All test controls</span></div>
    <details class="setting-group" open><summary>Experiment & J1979-2 traffic</summary><div class="settings-grid"><label>Architecture<select id="mp2Architecture"><option value="all" selected>Compare both</option><option value="distributed_canfd">Legacy distributed only</option><option value="zonal_hpc_proxy">Zonal application proxy only</option></select></label><label>J1979-2 service<select id="mp2J1979Service"><option value="mixed" selected>Mixed: 0x22 / 0x19 / 0x31 / 0x14</option><option value="read_data">0x22 ReadDataByIdentifier</option><option value="read_dtc">0x19 ReadDTCInformation</option><option value="clear_dtc">0x14 ClearDiagnosticInformation</option><option value="routine_control">0x31 RoutineControl</option></select></label><label>Traffic pattern<select id="mp2TrafficPattern"><option value="round_robin" selected>Sequential round-robin</option><option value="parallel4">4-way concurrent</option></select></label><label>Requests / architecture<input id="mp2Samples" type="number" min="12" max="5000" step="4" value="500"/></label><label>P2Tester budget (ms)<input id="mp2Budget" type="number" min="1" max="5000" value="50"/></label></div></details>
    <details class="setting-group" open><summary>Diagnostic server & compute load</summary><div class="settings-grid"><label>ECU / ZCU processing profile<select id="mp2Profile"><option value="nominal">Nominal — 20 ms mean</option><option value="near_limit">Near-limit — 38 ms mean</option><option value="custom">Custom</option></select></label><label>HPC proxy workload (ms)<input id="mp2ProxyWork" type="number" min="0" max="50" step="0.1" value="0"/></label><label>Gateway CPU pressure (%)<input id="mp2GatewayCpu" type="number" min="0" max="95" step="5" value="10"/></label><label>Legacy ECU CPU pressure (%)<input id="mp2LegacyEcuCpu" type="number" min="0" max="95" step="5" value="20"/></label><label>Graviton HPC CPU pressure (%)<input id="mp2HpcCpu" type="number" min="0" max="95" step="5" value="20"/></label><label>ZCU CPU pressure (%)<input id="mp2ZcuCpu" type="number" min="0" max="95" step="5" value="20"/></label></div><div id="mp2Custom" class="settings-grid custom-settings" hidden><label>Processing mean (ms)<input id="mp2Mean" type="number" step="0.1" value="38"/></label><label>σ (ms)<input id="mp2Sigma" type="number" step="0.1" value="5"/></label><label>Minimum (ms)<input id="mp2Min" type="number" step="0.1" value="20"/></label><label>Maximum (ms)<input id="mp2Max" type="number" step="0.1" value="49"/></label></div></details>
    <div class="network-settings-grid"><details class="setting-group" open><summary>Legacy CAN-FD</summary><div class="settings-grid compact-grid"><label>Bus A load — ECU 1 + 2 (%)<input id="mp2CanLoadA" type="number" min="0" max="90" step="5" value="50"/></label><label>Bus B load — ECU 3 (%)<input id="mp2CanLoadB" type="number" min="0" max="90" step="5" value="30"/></label><label>Bus C load — ECU 4 (%)<input id="mp2CanLoadC" type="number" min="0" max="90" step="5" value="15"/></label><label>Arbitration rate (kbit/s)<input id="mp2CanArb" type="number" min="125" max="1000" step="125" value="500"/></label><label>Data rate (Mbit/s)<input id="mp2CanData" type="number" min="1" max="8" step="1" value="2"/></label></div></details><details class="setting-group" open><summary>Zonal automotive Ethernet</summary><div class="settings-grid compact-grid"><label>Link rate<select id="mp2EthRate"><option value="100">100 Mbit/s</option><option value="1000" selected>1 Gbit/s</option></select></label><label>Link load (%)<input id="mp2EthLoad" type="number" min="0" max="90" step="5" value="20"/></label></div></details></div>
    <div class="run-bar"><label class="check"><span>Auto-stop EC2 nodes after run</span><input id="mp2AutoStop" type="checkbox" checked/></label><button id="runP2Measured">Run Benchmark</button><p id="p2MeasuredRunStatus">Start the fleet, then run.</p></div><p class="benchmark-caveat">Real AWS VPC + DoIP framing. CAN-FD/Ethernet load and vehicle-class CPU pressure are controlled emulations. J1979-2 data is synthetic; this is not a conformance test.</p>`;

  const profile = $('mp2Profile'), custom = $('mp2Custom');
  profile.onchange = () => { custom.hidden = profile.value !== 'custom'; };
  const resultsSection = $('p2MeasuredResults')?.closest('section'); if (resultsSection) { resultsSection.classList.add('benchmark-results'); resultsSection.querySelector('h2').textContent='04 · Results'; }
  const perServerSection = $('p2MeasuredPerServer')?.closest('section'); if (perServerSection) { perServerSection.className='panel result-details'; perServerSection.innerHTML=`<details open><summary>Detailed breakdown</summary><h3>Per ECU / ZCU</h3><div id="p2MeasuredPerServer" class="breakdown-grid"><p>No measured results yet.</p></div><h3>Per J1979-2 service</h3><div id="p2MeasuredPerService" class="breakdown-grid"><p>No measured results yet.</p></div></details>`; }
  const histogramSection = $('p2MeasuredHistograms')?.closest('section'); if (histogramSection) { histogramSection.className='panel result-details'; histogramSection.innerHTML=`<details><summary>Latency distributions</summary><div id="p2MeasuredHistograms"></div></details>`; }

  function num(id){return Number($(id).value);} function bodyV3(){const body={architecture:$('mp2Architecture').value,profile:$('mp2Profile').value,budget_ms:num('mp2Budget'),samples:num('mp2Samples'),proxy_work_ms:num('mp2ProxyWork'),j1979_service:$('mp2J1979Service').value,traffic_pattern:$('mp2TrafficPattern').value,can_load_a:num('mp2CanLoadA')/100,can_load_b:num('mp2CanLoadB')/100,can_load_c:num('mp2CanLoadC')/100,can_arb_bps:num('mp2CanArb')*1000,can_data_bps:num('mp2CanData')*1000000,ethernet_rate_mbps:num('mp2EthRate'),ethernet_load:num('mp2EthLoad')/100,gateway_cpu_pressure_pct:num('mp2GatewayCpu'),legacy_ecu_cpu_pressure_pct:num('mp2LegacyEcuCpu'),hpc_cpu_pressure_pct:num('mp2HpcCpu'),zcu_cpu_pressure_pct:num('mp2ZcuCpu'),auto_stop:$('mp2AutoStop').checked};if(body.profile==='custom')body.custom_server={mean_ms:num('mp2Mean'),sigma_ms:num('mp2Sigma'),minimum_ms:num('mp2Min'),maximum_ms:num('mp2Max')};return body;}
  function renderServices(results){const target=$('p2MeasuredPerService');if(!target)return;const labels={read_data:'0x22 ReadDataByIdentifier',read_dtc:'0x19 ReadDTCInformation',clear_dtc:'0x14 ClearDiagnosticInformation',routine_control:'0x31 RoutineControl'};target.innerHTML=results.map(r=>{const rows=Object.entries(r.per_service_p2tester_ms||{}).map(([service,s])=>`<li><span>${labels[service]||service} P99</span><strong>${Number(s.p99).toFixed(3)} ms</strong></li>`).join('');return `<article class="breakdown-card"><h3>${r.label}</h3><ul>${rows||'<li>No service data</li>'}</ul></article>`;}).join('');}
  async function pollV3(runId){const status=$('p2MeasuredRunStatus');for(let i=0;i<500;i++){try{const envelope=await window.call(`/p2/measured/results/${runId}`);if(envelope.complete&&envelope.result){window.renderMeasured(envelope.result);renderServices(envelope.result.results||[]);status.textContent=`Run ${runId} complete.`;window.setStatus('Measured two-architecture benchmark complete.','success');return;}if(envelope.error){const detail=window.commandFailureText?window.commandFailureText(envelope):envelope.error;throw new Error(detail);}const commandText=Object.entries(envelope.commands||{}).map(([r,s])=>`${r}:${s.status}`).join(' · ');status.textContent=`Running ${runId} · ${commandText}`;}catch(e){status.textContent=e.message;window.setStatus(e.message,'error');return;}await new Promise(resolve=>setTimeout(resolve,3000));}status.textContent='Timed out waiting for measured results.';}
  $('runP2Measured').onclick=async()=>{const status=$('p2MeasuredRunStatus');try{const body=bodyV3();status.textContent='Launching benchmark…';window.setStatus('Starting measured two-architecture benchmark…','working');const result=await window.call('/p2/measured/run',{method:'POST',body:JSON.stringify(body)});status.textContent=`Run ${result.run_id} started on DoIP TCP/${result.port}.`;pollV3(result.run_id);}catch(e){status.textContent=e.message;window.setStatus(e.message,'error');}};
})();
