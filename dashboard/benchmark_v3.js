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
      <p>Compare tester-observed P2 timing across the same four diagnostic endpoints.</p>`;
  }

  const paths = measuredView.querySelector('.architecture-paths');
  if (paths) {
    paths.className = 'panel benchmark-architecture';
    paths.innerHTML = `
      <div class="section-heading">
        <div><p class="eyebrow">01 · Architecture</p><h2>Vehicle Network Under Test</h2></div>
        <span class="test-badge">DoIP · J1979-2 service traffic</span>
      </div>
      <div style="border:1px solid #d8dee8;border-radius:14px;overflow:hidden;background:#fff">
        <img src="benchmark-architecture.svg" alt="Distributed legacy gateway with three CAN-FD buses and four ECUs compared with a Graviton HPC application proxy connected by automotive Ethernet to four ZCUs" style="display:block;width:100%;height:auto" />
      </div>`;
  }

  const nodeGrid = measuredView.querySelector('.p2-node-grid');
  const fleetActions = measuredView.querySelector('.fleet-actions');
  if (nodeGrid) {
    nodeGrid.className = 'panel fleet-panel';
    nodeGrid.innerHTML = `
      <div class="section-heading">
        <div><p class="eyebrow">02 · Fleet</p><h2>EC2 Benchmark Nodes</h2></div>
        <div id="benchmarkFleetActions"></div>
      </div>
      <div class="table-wrap">
        <table class="fleet-table">
          <thead><tr><th>Role</th><th>Status</th><th>Instance</th></tr></thead>
          <tbody>
            <tr><td>Tester</td><td id="p2TesterState">Unknown</td><td id="p2TesterType">—</td></tr>
            <tr><td>Legacy gateway</td><td id="p2LegacyGatewayState">Unknown</td><td id="p2LegacyGatewayType">—</td></tr>
            <tr><td>4 × Legacy ECU</td><td id="p2LegacyEcuState">Unknown</td><td id="p2LegacyEcuType">—</td></tr>
            <tr><td>Graviton HPC</td><td id="p2HpcState">Unknown</td><td id="p2HpcType">—</td></tr>
            <tr><td>4 × ZCU</td><td id="p2ZcuState">Unknown</td><td id="p2ZcuType">—</td></tr>
          </tbody>
        </table>
      </div>`;
    const slot = $('benchmarkFleetActions');
    if (fleetActions && slot) {
      fleetActions.classList.remove('panel');
      fleetActions.classList.add('compact-actions');
      slot.replaceWith(fleetActions);
    }
  }

  const oldConfig = $('mp2Architecture')?.closest('section');
  if (!oldConfig) return;
  oldConfig.className = 'panel benchmark-settings';
  oldConfig.innerHTML = `
    <div class="section-heading">
      <div><p class="eyebrow">03 · Configure</p><h2>Benchmark Settings</h2></div>
      <span class="settings-count">All test controls</span>
    </div>

    <details class="setting-group" open>
      <summary>Experiment & J1979-2 traffic</summary>
      <div class="settings-grid">
        <label>Architecture
          <select id="mp2Architecture">
            <option value="all">Compare both</option>
            <option value="distributed_canfd">Legacy distributed</option>
            <option value="zonal_hpc_proxy">Zonal application proxy</option>
          </select>
        </label>
        <label>J1979-2 service
          <select id="mp2J1979Service">
            <option value="mixed" selected>Mixed: 0x22 / 0x19 / 0x31 / 0x14</option>
            <option value="read_data">0x22 ReadDataByIdentifier</option>
            <option value="read_dtc">0x19 ReadDTCInformation</option>
            <option value="clear_dtc">0x14 ClearDiagnosticInformation</option>
            <option value="routine_control">0x31 RoutineControl</option>
          </select>
        </label>
        <label>Traffic pattern
          <select id="mp2TrafficPattern">
            <option value="round_robin" selected>Sequential round-robin</option>
            <option value="parallel4">4-way concurrent</option>
          </select>
        </label>
        <label>Requests / architecture<input id="mp2Samples" type="number" min="12" max="5000" step="4" value="500" /></label>
        <label>P2Tester budget (ms)<input id="mp2Budget" type="number" min="1" max="5000" value="50" /></label>
      </div>
    </details>

    <details class="setting-group" open>
      <summary>Diagnostic server & compute load</summary>
      <div class="settings-grid">
        <label>ECU / ZCU processing profile
          <select id="mp2Profile">
            <option value="nominal">Nominal — 20 ms mean</option>
            <option value="near_limit">Near-limit — 38 ms mean</option>
            <option value="custom">Custom</option>
          </select>
        </label>
        <label>HPC proxy workload (ms)<input id="mp2ProxyWork" type="number" min="0" max="50" step="0.1" value="0" /></label>
        <label>Gateway CPU pressure (%)<input id="mp2GatewayCpu" type="number" min="0" max="95" step="5" value="10" /></label>
        <label>Legacy ECU CPU pressure (%)<input id="mp2LegacyEcuCpu" type="number" min="0" max="95" step="5" value="20" /></label>
        <label>Graviton HPC CPU pressure (%)<input id="mp2HpcCpu" type="number" min="0" max="95" step="5" value="20" /></label>
        <label>ZCU CPU pressure (%)<input id="mp2ZcuCpu" type="number" min="0" max="95" step="5" value="20" /></label>
      </div>
      <div id="mp2Custom" class="settings-grid custom-settings" hidden>
        <label>Processing mean (ms)<input id="mp2Mean" type="number" step="0.1" value="38" /></label>
        <label>σ (ms)<input id="mp2Sigma" type="number" step="0.1" value="5" /></label>
        <label>Minimum (ms)<input id="mp2Min" type="number" step="0.1" value="20" /></label>
        <label>Maximum (ms)<input id="mp2Max" type="number" step="0.1" value="49" /></label>
      </div>
    </details>

    <div class="network-settings-grid">
      <details class="setting-group" open>
        <summary>Legacy CAN-FD</summary>
        <div class="settings-grid compact-grid">
          <label>Bus A load — ECU 1 + 2 (%)<input id="mp2CanLoadA" type="number" min="0" max="90" step="5" value="50" /></label>
          <label>Bus B load — ECU 3 (%)<input id="mp2CanLoadB" type="number" min="0" max="90" step="5" value="30" /></label>
          <label>Bus C load — ECU 4 (%)<input id="mp2CanLoadC" type="number" min="0" max="90" step="5" value="15" /></label>
          <label>Arbitration rate (kbit/s)<input id="mp2CanArb" type="number" min="125" max="1000" step="125" value="500" /></label>
          <label>Data rate (Mbit/s)<input id="mp2CanData" type="number" min="1" max="8" step="1" value="2" /></label>
        </div>
      </details>

      <details class="setting-group" open>
        <summary>Zonal automotive Ethernet</summary>
        <div class="settings-grid compact-grid">
          <label>Link rate
            <select id="mp2EthRate"><option value="100">100 Mbit/s</option><option value="1000" selected>1 Gbit/s</option></select>
          </label>
          <label>Link load (%)<input id="mp2EthLoad" type="number" min="0" max="90" step="5" value="20" /></label>
        </div>
      </details>
    </div>

    <div class="run-bar">
      <label class="check"><span>Auto-stop EC2 nodes after run</span><input id="mp2AutoStop" type="checkbox" checked /></label>
      <button id="runP2Measured">Run Benchmark</button>
      <p id="p2MeasuredRunStatus">Start the fleet, then run.</p>
    </div>
    <p class="benchmark-caveat">Real AWS VPC + DoIP framing. CAN-FD/Ethernet load and vehicle-class CPU pressure are controlled emulations. J1979-2 data is synthetic; this is not a conformance test.</p>`;

  const profile = $('mp2Profile');
  const custom = $('mp2Custom');
  profile.onchange = () => { custom.hidden = profile.value !== 'custom'; };

  const resultsSection = $('p2MeasuredResults')?.closest('section');
  if (resultsSection) {
    resultsSection.classList.add('benchmark-results');
    resultsSection.querySelector('h2').textContent = '04 · Results';
  }

  const perServerSection = $('p2MeasuredPerServer')?.closest('section');
  if (perServerSection) {
    perServerSection.className = 'panel result-details';
    perServerSection.innerHTML = `
      <details open>
        <summary>Detailed breakdown</summary>
        <h3>Per ECU / ZCU</h3>
        <div id="p2MeasuredPerServer" class="breakdown-grid"><p>No measured results yet.</p></div>
        <h3>Per J1979-2 service</h3>
        <div id="p2MeasuredPerService" class="breakdown-grid"><p>No measured results yet.</p></div>
      </details>`;
  }

  const histogramSection = $('p2MeasuredHistograms')?.closest('section');
  if (histogramSection) {
    histogramSection.className = 'panel result-details';
    histogramSection.innerHTML = `
      <details>
        <summary>Latency distributions</summary>
        <div id="p2MeasuredHistograms"></div>
      </details>`;
  }

  function num(id) { return Number($(id).value); }
  function bodyV3() {
    const body = {
      architecture: $('mp2Architecture').value,
      profile: $('mp2Profile').value,
      budget_ms: num('mp2Budget'),
      samples: num('mp2Samples'),
      proxy_work_ms: num('mp2ProxyWork'),
      j1979_service: $('mp2J1979Service').value,
      traffic_pattern: $('mp2TrafficPattern').value,
      can_load_a: num('mp2CanLoadA') / 100,
      can_load_b: num('mp2CanLoadB') / 100,
      can_load_c: num('mp2CanLoadC') / 100,
      can_arb_bps: num('mp2CanArb') * 1000,
      can_data_bps: num('mp2CanData') * 1000000,
      ethernet_rate_mbps: num('mp2EthRate'),
      ethernet_load: num('mp2EthLoad') / 100,
      gateway_cpu_pressure_pct: num('mp2GatewayCpu'),
      legacy_ecu_cpu_pressure_pct: num('mp2LegacyEcuCpu'),
      hpc_cpu_pressure_pct: num('mp2HpcCpu'),
      zcu_cpu_pressure_pct: num('mp2ZcuCpu'),
      auto_stop: $('mp2AutoStop').checked,
    };
    if (body.profile === 'custom') {
      body.custom_server = {
        mean_ms: num('mp2Mean'), sigma_ms: num('mp2Sigma'),
        minimum_ms: num('mp2Min'), maximum_ms: num('mp2Max'),
      };
    }
    return body;
  }

  function renderServices(results) {
    const target = $('p2MeasuredPerService');
    if (!target) return;
    const labels = {
      read_data: '0x22 ReadDataByIdentifier',
      read_dtc: '0x19 ReadDTCInformation',
      clear_dtc: '0x14 ClearDiagnosticInformation',
      routine_control: '0x31 RoutineControl',
    };
    target.innerHTML = results.map(r => {
      const rows = Object.entries(r.per_service_p2tester_ms || {}).map(([service, s]) =>
        `<li><span>${labels[service] || service} P99</span><strong>${Number(s.p99).toFixed(3)} ms</strong></li>`
      ).join('');
      return `<article class="breakdown-card"><h3>${r.label}</h3><ul>${rows || '<li>No service data</li>'}</ul></article>`;
    }).join('');
  }

  async function pollV3(runId) {
    const status = $('p2MeasuredRunStatus');
    for (let i = 0; i < 500; i++) {
      try {
        const envelope = await window.call(`/p2/measured/results/${runId}`);
        if (envelope.complete && envelope.result) {
          window.renderMeasured(envelope.result);
          renderServices(envelope.result.results || []);
          status.textContent = `Run ${runId} complete.`;
          window.setStatus('Measured architecture benchmark complete.', 'success');
          return;
        }
        if (envelope.error) {
          const detail = window.commandFailureText ? window.commandFailureText(envelope) : envelope.error;
          throw new Error(detail);
        }
        const commandText = Object.entries(envelope.commands || {}).map(([r, s]) => `${r}:${s.status}`).join(' · ');
        status.textContent = `Running ${runId} · ${commandText}`;
      } catch (e) {
        status.textContent = e.message;
        window.setStatus(e.message, 'error');
        return;
      }
      await new Promise(resolve => setTimeout(resolve, 3000));
    }
    status.textContent = 'Timed out waiting for measured results.';
  }

  $('runP2Measured').onclick = async () => {
    const status = $('p2MeasuredRunStatus');
    try {
      const body = bodyV3();
      status.textContent = 'Launching benchmark…';
      window.setStatus('Starting measured architecture benchmark…', 'working');
      const result = await window.call('/p2/measured/run', {method: 'POST', body: JSON.stringify(body)});
      status.textContent = `Run ${result.run_id} started · TCP/${result.port}`;
      pollV3(result.run_id);
    } catch (e) {
      status.textContent = e.message;
      window.setStatus(e.message, 'error');
    }
  };

  if (window.refreshP2Nodes && $('apiBase')?.value && $('token')?.value) window.refreshP2Nodes();
})();