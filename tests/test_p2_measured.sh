#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="/tmp/p2-measured-test.json"
PORT=15400
LEGACY_GW_IP=127.0.0.2
HPC_IP=127.0.0.3
PIDS=()
cleanup() {
  for pid in "${PIDS[@]:-}"; do kill "$pid" 2>/dev/null || true; done
}
trap cleanup EXIT

for i in 1 2 3 4; do
  port=$((15500+i))
  python3 "$ROOT/diagnostic_timing/aws_measured/p2_diag_server.py" \
    --role legacy_ecu --zone-id "$i" --logical-address "$((0x1000+i))" \
    --host 127.0.0.1 --port "$port" --mean-ms 1 --sigma-ms 0.1 --min-ms 0.5 --max-ms 2 --idle-timeout-s 20 &
  PIDS+=("$!")
done

for i in 1 2 3 4; do
  port=$((15600+i))
  python3 "$ROOT/diagnostic_timing/aws_measured/p2_diag_server.py" \
    --role zcu --zone-id "$i" --logical-address "$((0x2000+i))" \
    --host 127.0.0.1 --port "$port" --mean-ms 1 --sigma-ms 0.1 --min-ms 0.5 --max-ms 2 --idle-timeout-s 20 &
  PIDS+=("$!")
done

python3 "$ROOT/diagnostic_timing/aws_measured/p2_router.py" \
  --role legacy_gateway --entity-address 0x0D00 --host "$LEGACY_GW_IP" --port "$PORT" \
  --route 0x1001=127.0.0.1:15501 --route 0x1002=127.0.0.1:15502 \
  --route 0x1003=127.0.0.1:15503 --route 0x1004=127.0.0.1:15504 \
  --can-load 0.2 --idle-timeout-s 20 &
PIDS+=("$!")

python3 "$ROOT/diagnostic_timing/aws_measured/p2_router.py" \
  --role hpc --entity-address 0x0A00 --host "$HPC_IP" --port "$PORT" \
  --route 0x2001=127.0.0.1:15601 --route 0x2002=127.0.0.1:15602 \
  --route 0x2003=127.0.0.1:15603 --route 0x2004=127.0.0.1:15604 \
  --proxy-route 0x3001=0x2001@127.0.0.1:15601 --proxy-route 0x3002=0x2002@127.0.0.1:15602 \
  --proxy-route 0x3003=0x2003@127.0.0.1:15603 --proxy-route 0x3004=0x2004@127.0.0.1:15604 \
  --proxy-work-ms 0.2 --idle-timeout-s 20 &
PIDS+=("$!")

sleep 0.7
python3 "$ROOT/diagnostic_timing/aws_measured/p2_tester.py" \
  --architecture all --legacy-gateway-ip "$LEGACY_GW_IP" --hpc-ip "$HPC_IP" --port "$PORT" \
  --samples 24 --budget-ms 20 --output "$OUT"

python3 - "$OUT" <<'PY'
import json, sys
payload = json.load(open(sys.argv[1]))
assert payload["mode"] == "measured_aws_vehicle_architecture"
assert len(payload["results"]) == 3
by_name = {r["architecture"]: r for r in payload["results"]}
assert set(by_name) == {"distributed_canfd", "zonal_transparent", "zonal_hpc_proxy"}
for result in by_name.values():
    assert result["samples"] == 24
    assert result["p2tester_elapsed_ms"]["mean"] > 0
    assert len(result["histogram"]) == 32
    assert result["trace"]
    assert set(result["per_server_p2tester_ms"]) == {"1", "2", "3", "4"}
    assert result["trace"][0]["uds_request"] == "22F190"
assert "4 ECUs" in by_name["distributed_canfd"]["label"]
assert "4 ZCUs" in by_name["zonal_transparent"]["label"]
assert "application proxy" in by_name["zonal_hpc_proxy"]["label"]
print("four-ECU/four-ZCU DoIP measured P2 integration test passed")
PY
