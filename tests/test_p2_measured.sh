#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="/tmp/p2-measured-test.json"
PORT=15400
HPC_IP=127.0.0.2
ZONE_IP=127.0.0.3
TARGET_IP=127.0.0.4
PIDS=()
cleanup() {
  for pid in "${PIDS[@]:-}"; do kill "$pid" 2>/dev/null || true; done
}
trap cleanup EXIT

python3 "$ROOT/diagnostic_timing/aws_measured/p2_target_ecu.py" \
  --host "$TARGET_IP" --port "$PORT" --mean-ms 1 --sigma-ms 0.1 --min-ms 0.5 --max-ms 2 --idle-timeout-s 20 &
PIDS+=("$!")
python3 "$ROOT/diagnostic_timing/aws_measured/p2_relay.py" \
  --role zone --host "$ZONE_IP" --port "$PORT" --downstream-host "$TARGET_IP" --downstream-port "$PORT" --idle-timeout-s 20 &
PIDS+=("$!")
python3 "$ROOT/diagnostic_timing/aws_measured/p2_relay.py" \
  --role hpc --host "$HPC_IP" --port "$PORT" --downstream-host "$ZONE_IP" --downstream-port "$PORT" --proxy-work-ms 0.2 --idle-timeout-s 20 &
PIDS+=("$!")

sleep 0.5
python3 "$ROOT/diagnostic_timing/aws_measured/p2_tester.py" \
  --architecture all --hpc-ip "$HPC_IP" --zone-ip "$ZONE_IP" --port "$PORT" \
  --samples 30 --budget-ms 20 --output "$OUT"

python3 - "$OUT" <<'PY'
import json, sys
payload = json.load(open(sys.argv[1]))
assert payload["mode"] == "measured_aws_vpc"
assert len(payload["results"]) == 3
by_name = {r["architecture"]: r for r in payload["results"]}
assert set(by_name) == {"distributed_canfd", "zonal_transparent", "zonal_hpc_proxy"}
for result in by_name.values():
    assert result["samples"] == 30
    assert result["p2tester_elapsed_ms"]["mean"] > 0
    assert result["server_processing_ms"]["mean"] > 0
    assert len(result["histogram"]) == 32
    assert result["trace"]
assert by_name["zonal_hpc_proxy"]["architecture_delay_ms"]["mean_components"]["hpc_local_processing"] > 0
print("measured P2 integration test passed")
PY
