# OBDonUDS P2Tester Timing — Distributed vs Zonal Architecture

This scenario asks a concrete architecture question:

> Can a zonal OBDonUDS architecture satisfy a 50 ms external-tester response budget when requests are routed through an HPC and zone controller, and how does that compare with a distributed gateway architecture?

The study is intentionally separated from the ESC SIL scenario but reuses the same AWS automotive lab repository and can later reuse its EC2/VPC/dashboard infrastructure.

## Standards framing

SAE J1979-2 defines OBDonUDS communication between vehicle OBD systems and external generic test equipment. ISO 14229 timing separates target-server processing from architecture-dependent network delay. The simulator therefore models:

`P2Tester observed elapsed time = target ECU processing + architecture/network delay`

The default 50 ms project budget is the timing requirement under study. The component-delay distributions in this repository are engineering assumptions, not normative SAE/ISO values.

## Architectures

### 1. Distributed gateway + CAN-FD

```text
Tester / DoIP
    |
Diagnostic gateway
    |
CAN-FD
    |
Target ECU
```

Main delay risks: gateway software, CAN-FD arbitration/queueing, bus load, multi-frame transfer.

### 2. Zonal transparent Ethernet routing

```text
Tester / DoIP
    |
Central/HPC Ethernet forwarding
    |
Automotive Ethernet switches
    |
Zone controller
    |
Target ECU
```

The HPC/central compute does not terminate and regenerate the diagnostic service; it primarily routes traffic. Extra Ethernet hops are normally small compared with ECU processing and a loaded CAN last mile.

### 3. Zonal HPC diagnostic proxy

```text
Tester / DoIP
    |
HPC diagnostic service / proxy
    |  terminate, schedule, route, regenerate
Zone controller
    |
Target ECU
```

This is the architecture most likely to consume meaningful P2Tester margin because application scheduling, service lookup, authorization, IPC, queueing, and response reassembly can add milliseconds and jitter.

## Default engineering assumptions

The simulator exposes every assumption in `p2_latency_sim.py` so it can be replaced with real measurements.

Nominal target-ECU processing profile:
- mean: approximately 20 ms
- standard deviation: 7 ms
- clipped to 3–45 ms

Near-limit target-ECU profile:
- mean: approximately 38 ms
- standard deviation: 5 ms
- clipped to 20–49 ms

Representative median delay assumptions:
- external DoIP path: 0.25 ms each way
- software gateway: 0.35 ms each way
- CAN-FD last mile: 1.2 ms each way
- Ethernet switching hop: 0.08 ms each way
- zone forwarding: 0.15 ms each way
- HPC proxy scheduling/processing: 1.5 ms request side + 1.5 ms response side, with deliberately high jitter

These are starting hypotheses for a trade study, not standards values.

## Run

```bash
python3 diagnostic_timing/p2_latency_sim.py --profile nominal --samples 100000
python3 diagnostic_timing/p2_latency_sim.py --profile near_limit --samples 100000
```

The output reports:
- mean/P95/P99 architecture delay
- mean/P95/P99 observed P2Tester elapsed time
- 50 ms budget miss count and percentage
- mean contribution of each delay component

## Expected engineering conclusion

A zonal architecture is not inherently slower. A transparent Ethernet zonal path can be faster than a distributed path that finishes on CAN/CAN-FD. The architectural risk appears when the HPC becomes a diagnostic application proxy rather than a low-overhead router.

The 50 ms requirement becomes particularly sensitive when the target ECU already consumes most of the processing budget. The correct design question is therefore not simply “How many hops are there?” but:

1. How much of the P2Tester budget is consumed by the target ECU?
2. Does the HPC route packets or terminate/proxy the diagnostic service?
3. What are P95/P99 queueing and scheduling delays under realistic CPU/network load?
4. Is the target ECU reached through Ethernet, CAN-FD, or classic CAN?
5. What margin remains at the external tester under worst credible load?

## AWS experiment extension

The next phase can deploy four logical roles on AWS:

```text
External tester simulator
        |
   DoIP/TCP traffic
        |
Gateway / HPC router-or-proxy
        |
Zone controller / gateway
        |
Target ECU simulator
```

Each node timestamps request ingress/egress so the dashboard can plot the complete latency decomposition and compare nominal, loaded, and fault-injected conditions.