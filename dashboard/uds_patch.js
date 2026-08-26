(() => {
  const $ = id => document.getElementById(id);
  const measuredView = $('p2MeasuredView');
  if (!measuredView) return;

  const intro = document.querySelector('#p2Lab .lab-intro');
  if (intro) {
    intro.innerHTML = `
      <p class="eyebrow">Measured AWS benchmark</p>
      <h2>Legacy Distributed vs Zonal HPC Application Proxy</h2>
      <p>Compare tester-observed P2 timing using UDS diagnostic traffic over DoIP.</p>`;
  }

  const paths = measuredView.querySelector('.benchmark-architecture, .architecture-paths');
  if (paths) {
    paths.className = 'panel benchmark-architecture';
    paths.innerHTML = `
      <div class="section-heading">
        <div><p class="eyebrow">01 · Architecture</p><h2>Vehicle Networks Under Test</h2></div>
        <span class="test-badge">UDS over DoIP diagnostic traffic</span>
      </div>
      <div class="architecture-grid">
        <article class="architecture-card legacy-card">
          <div class="architecture-card-title">Distributed / Legacy</div>
          <svg class="architecture-svg" viewBox="0 0 620 310" role="img" aria-label="Legacy distributed architecture: external diagnostic tester to central gateway to three CAN-FD buses and four ECUs">
            <rect class="svg-node" x="20" y="120" width="105" height="62" rx="8"/><text class="svg-label" x="72" y="144">Diagnostic</text><text class="svg-label" x="72" y="162">Tester</text>
            <line class="svg-doip" x1="125" y1="151" x2="185" y2="151"/><text class="svg-edge-label" x="155" y="136">UDS / DoIP</text>
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
          <svg class="architecture-svg" viewBox="0 0 680 310" role="img" aria-label="Zonal architecture: external diagnostic tester through a logical DoIP security edge to the Graviton HPC UDS application proxy and four ZCUs">
            <rect class="svg-node" x="15" y="120" width="96" height="62" rx="8"/><text class="svg-label" x="63" y="144">Diagnostic</text><text class="svg-label" x="63" y="162">Tester</text>
            <line class="svg-doip svg-doip-zonal" x1="111" y1="151" x2="146" y2="151"/><text class="svg-edge-label" x="128" y="136">UDS / DoIP</text>
            <rect class="svg-node svg-gateway" x="146" y="111" width="112" height="80" rx="8"/><text class="svg-label" x="202" y="141">DoIP Edge</text><text class="svg-sub-label" x="202" y="162">security / routing</text>
            <line class="svg-eth" x1="258" y1="151" x2="292" y2="151"/>
            <rect class="svg-node svg-hpc" x="292" y="94" width="150" height="114" rx="9"/><text class="svg-label svg-hpc-label" x="367" y="128">Graviton HPC</text><text class="svg-label" x="367" y="151">UDS App Proxy</text><text class="svg-sub-label" x="367" y="176">terminate · process · reissue</text>
            <line class="svg-eth" x1="442" y1="151" x2="478" y2="151"/><line class="svg-eth" x1="478" y1="50" x2="478" y2="258"/>
            <line class="svg-eth" x1="478" y1="50" x2="560" y2="50"/><line class="svg-eth" x1="478" y1="118" x2="560" y2="118"/><line class="svg-eth" x1="478" y1="190" x2="560" y2="190"/><line class="svg-eth" x1="478" y1="258" x2="560" y2="258"/>
            <rect class="svg-node svg-zcu" x="560" y="25" width="105" height="50" rx="7"/><text class="svg-label" x="612" y="55">ZCU 1</text><rect class="svg-node svg-zcu" x="560" y="93" width="105" height="50" rx="7"/><text class="svg-label" x="612" y="123">ZCU 2</text><rect class="svg-node svg-zcu" x="560" y="165" width="105" height="50" rx="7"/><text class="svg-label" x="612" y="195">ZCU 3</text><rect class="svg-node svg-zcu" x="560" y="233" width="105" height="50" rx="7"/><text class="svg-label" x="612" y="263">ZCU 4</text>
            <text class="svg-network-note" x="478" y="295">Automotive Ethernet</text>
          </svg>
          <p class="benchmark-caveat">DoIP Edge is shown as the logical vehicle ingress/security layer. The current AWS measurement path does not use a separate EC2 instance for this layer.</p>
        </article>
      </div>`;
  }

  document.querySelectorAll('.setting-group summary').forEach(summary => {
    summary.textContent = summary.textContent.replace('Experiment & J1979-2 traffic', 'Experiment & UDS traffic');
  });

  const serviceSelect = $('mp2J1979Service');
  if (serviceSelect) {
    const label = serviceSelect.closest('label');
    if (label) label.childNodes[0].textContent = 'UDS service';
  }

  document.querySelectorAll('.result-details h3').forEach(h3 => {
    h3.textContent = h3.textContent.replace('Per J1979-2 service', 'Per UDS service');
  });

  document.querySelectorAll('.benchmark-caveat').forEach(note => {
    note.textContent = note.textContent
      .replace('J1979-2 data is synthetic; this is not a conformance test.', 'UDS service data is synthetic; this is not an ISO 14229 or ISO 13400 conformance test.');
  });
})();
