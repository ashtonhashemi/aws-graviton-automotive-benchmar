#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="/tmp/p2-measured-test.json"
TARGET_PORT=15402
ZONE_PORT=15401
HPC_PORT=15400
PIDS=()
cleanup() {
  for pid in "${PIDS[@]:-}"; do kill "$pid" 2>/dev/null || true; done
}
trap cleanup EXIT

python3 "$ROOT/diagnostic_timing/aws_measured/p2_target_ecu.py" \
  --host 127.0.0.1 --port "$TARGET_PORT" --mean-ms 1 --sigma-ms 0.1 --min-ms 0.5 --max-ms 2 --idle-timeout-s 20 &
PIDS+=("$!")
python3 "$ROOT/diagnostic_timing/aws_measured/p2_relay.py" \
  --role zone --host 127.0.0.1 --port "$ZONE_PORT" --downstream-host 127.0.0.1 --downstream-port "$TARGET_PORT" --idle-timeout-s 20 &
PIDS+=("$!")
python3 "$ROOT/diagnostic_timing/aws_measured/p2_relay.py" \
  --role hpc --host 127.0.0.1 --port "$HPC_PORT" --downstream-host 127.0.0.1 --downstream-port "$ZONE_PORT" --proxy-work-ms 0.2 --idle-timeout-s 20 &
PIDS+=("$!")

sleep 0.5
python3 "$ROOT/diagnostic_timing/aws_measured/p2_tester.py" \
  --architecture all --hpc-ip 127.0.0.1 --zone-ip 127.0.0.1 --port "$HPC_PORT" \
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
