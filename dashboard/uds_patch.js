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
          <svg class="architecture-svg" viewBox="0 0 660 330" role="img" aria-label="Legacy distributed architecture on Amazon Linux 2023 x86_64 EC2 nodes: diagnostic tester to central gateway to three CAN-FD buses and four ECUs">
            <rect class="svg-node" x="15" y="124" width="116" height="70" rx="8"/><text class="svg-label" x="73" y="146">Diagnostic Tester</text><text class="svg-sub-label" x="73" y="166">AL2023 · x86_64</text><text class="svg-sub-label" x="73" y="181">c7i.large</text>
            <line class="svg-doip" x1="131" y1="159" x2="193" y2="159"/><text class="svg-edge-label" x="162" y="143">UDS / DoIP</text>
            <rect class="svg-node svg-gateway" x="193" y="112" width="132" height="94" rx="8"/><text class="svg-label" x="259" y="140">Central Gateway</text><text class="svg-sub-label" x="259" y="160">AL2023 · x86_64</text><text class="svg-sub-label" x="259" y="177">c7i.large</text>
            <line class="svg-can" x1="325" y1="159" x2="365" y2="159"/><line class="svg-can" x1="365" y1="62" x2="365" y2="268"/>
            <rect class="svg-bus" x="380" y="47" width="76" height="34" rx="6"/><text class="svg-bus-label" x="418" y="68">Bus A</text><line class="svg-can" x1="365" y1="64" x2="380" y2="64"/><line class="svg-can" x1="456" y1="64" x2="485" y2="64"/><line class="svg-can" x1="470" y1="64" x2="470" y2="119"/><line class="svg-can" x1="470" y1="119" x2="485" y2="119"/>
            <rect class="svg-node svg-ecu" x="485" y="30" width="150" height="62" rx="7"/><text class="svg-label" x="560" y="53">ECU 1</text><text class="svg-sub-label" x="560" y="72">AL2023 · x86_64 · c7i</text>
            <rect class="svg-node svg-ecu" x="485" y="96" width="150" height="62" rx="7"/><text class="svg-label" x="560" y="119">ECU 2</text><text class="svg-sub-label" x="560" y="138">AL2023 · x86_64 · c7i</text>
            <rect class="svg-bus" x="380" y="169" width="76" height="34" rx="6"/><text class="svg-bus-label" x="418" y="190">Bus B</text><line class="svg-can" x1="365" y1="186" x2="380" y2="186"/><line class="svg-can" x1="456" y1="186" x2="485" y2="186"/><rect class="svg-node svg-ecu" x="485" y="163" width="150" height="62" rx="7"/><text class="svg-label" x="560" y="186">ECU 3</text><text class="svg-sub-label" x="560" y="205">AL2023 · x86_64 · c7i</text>
            <rect class="svg-bus" x="380" y="251" width="76" height="34" rx="6"/><text class="svg-bus-label" x="418" y="272">Bus C</text><line class="svg-can" x1="365" y1="268" x2="380" y2="268"/><line class="svg-can" x1="456" y1="268" x2="485" y2="268"/><rect class="svg-node svg-ecu" x="485" y="241" width="150" height="62" rx="7"/><text class="svg-label" x="560" y="264">ECU 4</text><text class="svg-sub-label" x="560" y="283">AL2023 · x86_64 · c7i</text>
            <text class="svg-network-note" x="365" y="319">CAN-FD timing emulation</text>
          </svg>
        </article>
        <article class="architecture-card zonal-card">
          <div class="architecture-card-title">Zonal / HPC Application Proxy</div>
          <svg class="architecture-svg" viewBox="0 0 730 330" role="img" aria-label="Zonal architecture: x86_64 diagnostic tester through a logical DoIP security edge to an Amazon Linux 2023 ARM64 Graviton HPC UDS application proxy and four x86_64 ZCUs">
            <rect class="svg-node" x="10" y="124" width="112" height="70" rx="8"/><text class="svg-label" x="66" y="146">Diagnostic Tester</text><text class="svg-sub-label" x="66" y="166">AL2023 · x86_64</text><text class="svg-sub-label" x="66" y="181">c7i.large</text>
            <line class="svg-doip svg-doip-zonal" x1="122" y1="159" x2="157" y2="159"/><text class="svg-edge-label" x="139" y="143">UDS / DoIP</text>
            <rect class="svg-node svg-gateway" x="157" y="119" width="116" height="80" rx="8"/><text class="svg-label" x="215" y="146">DoIP Edge</text><text class="svg-sub-label" x="215" y="166">security / routing</text><text class="svg-sub-label" x="215" y="182">logical layer</text>
            <line class="svg-eth" x1="273" y1="159" x2="303" y2="159"/>
            <rect class="svg-node svg-hpc" x="303" y="99" width="174" height="120" rx="9"/><text class="svg-label svg-hpc-label" x="390" y="126">Graviton HPC</text><text class="svg-label" x="390" y="148">UDS App Proxy</text><text class="svg-sub-label" x="390" y="170">AL2023 · ARM64</text><text class="svg-sub-label" x="390" y="187">c8g.large</text><text class="svg-sub-label" x="390" y="204">terminate · process · reissue</text>
            <line class="svg-eth" x1="477" y1="159" x2="510" y2="159"/><line class="svg-eth" x1="510" y1="55" x2="510" y2="270"/>
            <line class="svg-eth" x1="510" y1="55" x2="575" y2="55"/><line class="svg-eth" x1="510" y1="123" x2="575" y2="123"/><line class="svg-eth" x1="510" y1="195" x2="575" y2="195"/><line class="svg-eth" x1="510" y1="270" x2="575" y2="270"/>
            <rect class="svg-node svg-zcu" x="575" y="27" width="142" height="60" rx="7"/><text class="svg-label" x="646" y="49">ZCU 1</text><text class="svg-sub-label" x="646" y="69">AL2023 · x86_64 · c7i</text>
            <rect class="svg-node svg-zcu" x="575" y="95" width="142" height="60" rx="7"/><text class="svg-label" x="646" y="117">ZCU 2</text><text class="svg-sub-label" x="646" y="137">AL2023 · x86_64 · c7i</text>
            <rect class="svg-node svg-zcu" x="575" y="167" width="142" height="60" rx="7"/><text class="svg-label" x="646" y="189">ZCU 3</text><text class="svg-sub-label" x="646" y="209">AL2023 · x86_64 · c7i</text>
            <rect class="svg-node svg-zcu" x="575" y="242" width="142" height="60" rx="7"/><text class="svg-label" x="646" y="264">ZCU 4</text><text class="svg-sub-label" x="646" y="284">AL2023 · x86_64 · c7i</text>
            <text class="svg-network-note" x="510" y="319">Automotive Ethernet timing overlay on real AWS VPC</text>
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
    serviceSelect.id = 'mp2UdsService';
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
