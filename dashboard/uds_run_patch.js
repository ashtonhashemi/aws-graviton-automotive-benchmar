(() => {
  const $ = id => document.getElementById(id);
  const run = $('runP2Measured');
  const service = $('mp2UdsService');
  if (!run || !service || !window.call) return;

  const num = id => Number($(id).value);
  const buildBody = () => {
    const body = {
      architecture: $('mp2Architecture').value,
      profile: $('mp2Profile').value,
      budget_ms: num('mp2Budget'),
      samples: num('mp2Samples'),
      proxy_work_ms: num('mp2ProxyWork'),
      uds_service: service.value,
      // Compatibility for the currently deployed control plane; removed after Lambda rename deploys.
      j1979_service: service.value,
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
  };

  const renderServices = results => {
    const target = $('p2MeasuredPerService');
    if (!target) return;
    const labels = {
      read_data: '0x22 ReadDataByIdentifier',
      read_dtc: '0x19 ReadDTCInformation',
      clear_dtc: '0x14 ClearDiagnosticInformation',
      routine_control: '0x31 RoutineControl',
    };
    target.innerHTML = results.map(r => {
      const rows = Object.entries(r.per_service_p2tester_ms || {}).map(([name, s]) =>
        `<li><span>${labels[name] || name} P99</span><strong>${Number(s.p99).toFixed(3)} ms</strong></li>`
      ).join('');
      return `<article class="breakdown-card"><h3>${r.label}</h3><ul>${rows || '<li>No service data</li>'}</ul></article>`;
    }).join('');
  };

  const poll = async runId => {
    const status = $('p2MeasuredRunStatus');
    for (let i = 0; i < 500; i++) {
      try {
        const envelope = await window.call(`/p2/measured/results/${runId}`);
        if (envelope.complete && envelope.result) {
          window.renderMeasured(envelope.result);
          renderServices(envelope.result.results || []);
          status.textContent = `Run ${runId} complete.`;
          window.setStatus('UDS-over-DoIP architecture benchmark complete.', 'success');
          return;
        }
        if (envelope.error) throw new Error(envelope.error);
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
  };

  run.onclick = async () => {
    const status = $('p2MeasuredRunStatus');
    try {
      status.textContent = 'Launching UDS-over-DoIP benchmark…';
      window.setStatus('Starting UDS-over-DoIP architecture benchmark…', 'working');
      const result = await window.call('/p2/measured/run', {method: 'POST', body: JSON.stringify(buildBody())});
      status.textContent = `Run ${result.run_id} launched.`;
      await poll(result.run_id);
    } catch (e) {
      status.textContent = e.message;
      window.setStatus(e.message, 'error');
    }
  };
})();
