#!/usr/bin/env bash
set -euo pipefail

PORT=5505
ZCU_OUT=/tmp/esc-zcu-test.json
HPC_OUT=/tmp/esc-hpc-test.json
rm -f "$ZCU_OUT" "$HPC_OUT"

python3 network/zcu_esc.py --port "$PORT" --esc on --timeout 10 --output "$ZCU_OUT" &
ZCU_PID=$!
trap 'kill "$ZCU_PID" 2>/dev/null || true' EXIT
sleep 0.2
python3 network/hpc_vehicle.py --zcu-ip 127.0.0.1 --port "$PORT" --esc on --output "$HPC_OUT"
wait "$ZCU_PID"
trap - EXIT

python3 - <<'PY'
import json
from pathlib import Path
h = json.loads(Path('/tmp/esc-hpc-test.json').read_text())
z = json.loads(Path('/tmp/esc-zcu-test.json').read_text())
assert h['transport'].startswith('real bidirectional UDP')
assert h['packets_sent'] > 100
assert h['packets_received'] == h['packets_sent']
assert h['packets_lost'] == 0
assert z['transport'].startswith('real UDP')
assert z['packets_received'] >= h['packets_received']
assert z['hpc_source_private_ip'] == '127.0.0.1'
assert h['simulated_fmvss126_pass'] is True
print('UDP integration PASS:', h['packets_received'], 'control packets, mean RTT', h['network_rtt_ms_mean'], 'ms')
PY
