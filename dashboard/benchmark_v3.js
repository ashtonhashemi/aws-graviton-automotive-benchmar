(() => {
  const byId = id => document.getElementById(id);
  const measuredView = byId('p2MeasuredView');
  if (!measuredView) return;

  const paths = measuredView.querySelector('.architecture-paths');
  if (paths) {
    paths.innerHTML = `
      <h2>Benchmark Architecture Diagrams</h2>
      <div class="chart-card">
        <h3>Legacy distributed E/E architecture</h3>
        <pre style="overflow:auto;line-height:1.55">External OBD Tester
        │  DoIP / J1979-2 service request
        ▼
Central Gateway
   ├──── CAN-FD Bus A ──── ECU 1
   │                    └─ ECU 2
   ├──── CAN-FD Bus B ──── ECU 3
   └──── CAN-FD Bus C ──── ECU 4</pre>
      </div>
      <div class="chart-card">
        <h3>Zonal / HPC architecture</h3>
        <pre style="overflow:auto;line-height:1.55">External OBD Tester
        │  DoIP / J1979-2 service request
        ▼
AWS Graviton HPC
   ├──── Automotive Ethernet ──── ZCU 1
   ├──── Automotive Ethernet ──── ZCU 2
   ├──── Automotive Ethernet ──── ZCU 3
   └──── Automotive Ethernet ──── ZCU 4

Transparent mode: HPC routes the diagnostic message.
Application-proxy mode: HPC terminates, interprets and reissues the request.</pre>
      </div>
      <p class="small-note">The AWS VPC path is real. CAN-FD and in-vehicle Ethernet serialization/load are controlled timing overlays; no physical CAN or automotive Ethernet PHY is claimed.</p>`;
  }

  const configSection = byId('mp2Architecture')?.closest('section');
  if (!configSection) return;

  const oldCanLoad = byId('mp2CanLoad');
  if (oldCanLoad?.closest('label')) oldCanLoad.closest('label').hidden = true;

  const controls = document.createElement('div');
  controls.innerHTML = `
    <hr />
    <h3>SAE J1979-2 Service Traffic</h3>
    <div class="form-row">
      <label>J1979-2 service
        <select id="mp2J1979Service">
          <option value="mixed" selected>Mixed — 0x22 / 0x19 / 0x31 / 0x14</option>
          <option value="read_data">0x22 ReadDataByIdentifier</option>
          <option value="read_dtc">0x19 ReadDTCInformation</option>
          <option value="clear_dtc">0x14 ClearDiagnosticInformation</option>
          <option value="routine_control">0x31 RoutineControl</option>
        </select>
      </label>
      <label>Tester traffic pattern
        <select id="mp2TrafficPattern">
          <option value="round_robin" selected>Sequential round-robin across 4 servers</option>
          <option value="parallel4">4-way concurrent requests</option>
        </select>
      </label>
    </div>
    <p class="small-note">Service IDs follow the OBDonUDS service set. Lab DIDs, DTC records and routine values are synthetic; this is a timing/integration harness, not an SAE J1979-2/J1979DA conformance test.</p>

    <h3>Legacy Network — Three CAN-FD Buses</h3>
    <div class="form-row">
      <label>Bus A load — ECU 1 + 2 (%)<input id="mp2CanLoadA" type="number" min="0" max="90" step="5" value="50" /></label>
      <label>Bus B load — ECU 3 (%)<input id="mp2CanLoadB" type="number" min="0" max="90" step="5" value="30" /></label>
      <label>Bus C load — ECU 4 (%)<input id="mp2CanLoadC" type="number" min="0" max="90" step="5" value="15" /></label>
    </div>

    <h3>Zonal Network — Automotive Ethernet Overlay</h3>
    <div class="form-row">
      <label>Ethernet link rate
        <select id="mp2EthRate"><option value="100">100 Mbit/s</option><option value="1000" selected>1 Gbit/s</option></select>
      </label>
      <label>Ethernet link load (%)<input id="mp2EthLoad" type="number" min="0" max="90" step="5" value="20" /></label>
    </div>

    <h3>Compute / SoC Load Emulation</h3>
    <div class="form-row">
      <label>Legacy gateway CPU pressure (%)<input id="mp2GatewayCpu" type="number" min="0" max="95" step="5" value="10" /></label>
      <label>Legacy ECU CPU pressure (%)<input id="mp2LegacyEcuCpu" type="number" min="0" max="95" step="5" value="20" /></label>
      <label>Graviton HPC CPU pressure (%)<input id="mp2HpcCpu" type="number" min="0" max="95" step="5" value="20" /></label>
      <label>ZCU CPU pressure (%)<input id="mp2ZcuCpu" type="number" min="0" max="95" step="5" value="20" /></label>
    </div>
    <p class="small-note">These controls create synthetic CPU pressure on the actual EC2 hosts. The node cards above show the real EC2 instance type and CPU architecture used for each role.</p>`;
  configSection.insertBefore(controls, byId('runP2Measured'));

  const perServer = byId('p2MeasuredPerServer')?.closest('section');
  if (perServer) {
    const serviceSection = document.createElement('section');
    serviceSection.className = 'panel';
    serviceSection.innerHTML = '<h2>Per-Service P2Tester</h2><div id="p2MeasuredPerService" class="breakdown-grid"><p>No measured results yet.</p></div>';
    perServer.insertAdjacentElement('afterend', serviceSection);
  }

  function num(id) { return Number(byId(id).value); }
  function bodyV3() {
    const body = {
      architecture: byId('mp2Architecture').value,
      profile: byId('mp2Profile').value,
      budget_ms: num('mp2Budget'),
      samples: num('mp2Samples'),
      proxy_work_ms: num('mp2ProxyWork'),
      j1979_service: byId('mp2J1979Service').value,
      traffic_pattern: byId('mp2TrafficPattern').value,
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
      auto_stop: byId('mp2AutoStop').checked,
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
    const target = byId('p2MeasuredPerService');
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
    const status = byId('p2MeasuredRunStatus');
    for (let i = 0; i < 500; i++) {
      try {
        const envelope = await window.call(`/p2/measured/results/${runId}`);
        if (envelope.complete && envelope.result) {
          window.renderMeasured(envelope.result);
          renderServices(envelope.result.results || []);
          status.textContent = `Measured run ${runId} complete.`;
          window.setStatus('Measured J1979-2 architecture benchmark complete.', 'success');
          return;
        }
        if (envelope.error) {
          const detail = window.commandFailureText ? window.commandFailureText(envelope) : envelope.error;
          throw new Error(detail);
        }
        const commandText = Object.entries(envelope.commands || {}).map(([r, s]) => `${r}:${s.status}`).join(' · ');
        status.textContent = `Run ${runId} executing… ${commandText}`;
      } catch (e) {
        status.textContent = e.message;
        window.setStatus(e.message, 'error');
        return;
      }
      await new Promise(resolve => setTimeout(resolve, 3000));
    }
    status.textContent = 'Timed out waiting for measured results.';
  }

  const runButton = byId('runP2Measured');
  runButton.onclick = async () => {
    const status = byId('p2MeasuredRunStatus');
    try {
      const body = bodyV3();
      status.textContent = 'Launching configured legacy + zonal J1979-2 benchmark…';
      window.setStatus('Starting measured J1979-2 architecture benchmark…', 'working');
      const result = await window.call('/p2/measured/run', {method: 'POST', body: JSON.stringify(body)});
      status.textContent = `Run ${result.run_id} started on DoIP TCP/${result.port}.`;
      pollV3(result.run_id);
    } catch (e) {
      status.textContent = e.message;
      window.setStatus(e.message, 'error');
    }
  };
})();
