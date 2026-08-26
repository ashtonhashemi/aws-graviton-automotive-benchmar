#!/usr/bin/env python3
"""External OBDonUDS-style tester for the measured AWS architecture benchmark."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import math
import socket
import statistics
import threading
import time
from pathlib import Path

from doip_codec import (
    PT_DIAGNOSTIC_MESSAGE,
    PT_ROUTING_ACTIVATION_RESPONSE,
    ROUTING_ACTIVATION_SUCCESS,
    diagnostic_message,
    parse_diagnostic_message,
    parse_routing_activation_response,
    recv_frame,
    routing_activation_request,
)

TESTER_ADDRESS = 0x0E80
LEGACY_TARGETS = (0x1001, 0x1002, 0x1003, 0x1004)
PROXY_TARGETS = (0x3001, 0x3002, 0x3003, 0x3004)

LABELS = {
    "distributed_canfd": "Legacy distributed: Tester → Gateway → 4 ECUs",
    "zonal_hpc_proxy": "Zonal application proxy: Tester → Graviton HPC proxy → 4 ZCUs",
}

SERVICE_LABELS = {
    "read_data": "0x22 ReadDataByIdentifier",
    "read_dtc": "0x19 ReadDTCInformation",
    "clear_dtc": "0x14 ClearDiagnosticInformation",
    "routine_control": "0x31 RoutineControl",
    "mixed": "Mixed J1979-2 service cycle",
}
SERVICE_CYCLE = ("read_data", "read_dtc", "routine_control", "clear_dtc")


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(q * len(ordered)) - 1))
    return ordered[index]


def summary(values: list[float]) -> dict:
    return {
        "mean": round(statistics.fmean(values), 6),
        "p50": round(percentile(values, 0.50), 6),
        "p95": round(percentile(values, 0.95), 6),
        "p99": round(percentile(values, 0.99), 6),
        "max": round(max(values), 6),
    }


def histogram(values: list[float], budget_ms: float, bins: int = 32) -> list[dict]:
    upper = max(max(values), budget_ms * 1.20, 1.0)
    width = upper / bins
    counts = [0] * bins
    for value in values:
        counts[min(bins - 1, int(value / width))] += 1
    return [
        {"from_ms": round(i * width, 6), "to_ms": round((i + 1) * width, 6), "count": count}
        for i, count in enumerate(counts)
    ]


def service_for(sequence: int, selected: str) -> str:
    return SERVICE_CYCLE[sequence % len(SERVICE_CYCLE)] if selected == "mixed" else selected


def uds_request_for(service: str) -> bytes:
    if service == "read_data":
        return b"\x22\xF1\x90"
    if service == "read_dtc":
        return b"\x19\x42\xFF"
    if service == "clear_dtc":
        return b"\x14\xFF\xFF\xFF"
    if service == "routine_control":
        return b"\x31\x01\xF0\x01"
    raise ValueError(f"unsupported service {service}")


def validate_positive_response(service: str, uds: bytes) -> bool:
    expected_sid = {
        "read_data": 0x62,
        "read_dtc": 0x59,
        "clear_dtc": 0x54,
        "routine_control": 0x71,
    }[service]
    return bool(uds) and uds[0] == expected_sid


def connect_with_retry(host: str, port: int, timeout_s: float = 30.0) -> socket.socket:
    deadline = time.monotonic() + timeout_s
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(15.0)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        try:
            sock.connect((host, port))
            return sock
        except OSError as exc:
            last_error = exc
            sock.close()
            time.sleep(0.2)
    raise RuntimeError(f"cannot connect to {host}:{port}: {last_error}")


def activate(sock: socket.socket) -> None:
    sock.sendall(routing_activation_request(TESTER_ADDRESS))
    payload_type, payload = recv_frame(sock)
    if payload_type != PT_ROUTING_ACTIVATION_RESPONSE:
        raise RuntimeError("DoIP entity did not return routing activation response")
    client, _, code = parse_routing_activation_response(payload)
    if client != TESTER_ADDRESS or code != ROUTING_ACTIVATION_SUCCESS:
        raise RuntimeError(f"DoIP routing activation failed with code 0x{code:02X}")


def targets_for(name: str) -> tuple[int, ...]:
    return LEGACY_TARGETS if name == "distributed_canfd" else PROXY_TARGETS


def one_request(sock: socket.socket, target: int, service: str, sequence: int, architecture: str) -> dict:
    uds_request = uds_request_for(service)
    frame = diagnostic_message(TESTER_ADDRESS, target, uds_request)
    start_ns = time.perf_counter_ns()
    sock.sendall(frame)
    response_type, payload = recv_frame(sock)
    elapsed_ms = (time.perf_counter_ns() - start_ns) / 1_000_000.0
    if response_type != PT_DIAGNOSTIC_MESSAGE:
        raise RuntimeError(f"{architecture}: expected diagnostic response, got 0x{response_type:04X}")
    response_source, response_target, uds_response = parse_diagnostic_message(payload)
    if response_target != TESTER_ADDRESS:
        raise RuntimeError(f"{architecture}: response target 0x{response_target:04X} is not tester")
    if not validate_positive_response(service, uds_response):
        raise RuntimeError(f"{architecture}: unexpected response for {SERVICE_LABELS[service]}: {uds_response.hex()}")
    return {
        "sequence": sequence,
        "elapsed_ms": elapsed_ms,
        "target": target,
        "response_source": response_source,
        "service": service,
        "uds_request": uds_request,
        "uds_response": uds_response,
    }


def run_architecture(name: str, first_hop: str, port: int, samples: int, budget_ms: float, j1979_service: str, traffic_pattern: str) -> dict:
    elapsed_values: list[float] = []
    target_samples: dict[str, list[float]] = {str(i): [] for i in range(1, 5)}
    service_samples: dict[str, list[float]] = {key: [] for key in SERVICE_CYCLE}
    trace: list[dict] = []
    targets = targets_for(name)
    trace_lock = threading.Lock()

    def record(result: dict, server_index: int) -> None:
        elapsed = result["elapsed_ms"]
        elapsed_values.append(elapsed)
        target_samples[str(server_index)].append(elapsed)
        service_samples[result["service"]].append(elapsed)
        with trace_lock:
            if len(trace) < 500:
                trace.append({
                    "sequence": result["sequence"],
                    "server_index": server_index,
                    "service": result["service"],
                    "service_label": SERVICE_LABELS[result["service"]],
                    "tester_target_logical_address": f"0x{result['target']:04X}",
                    "response_source_logical_address": f"0x{result['response_source']:04X}",
                    "p2tester_ms": round(elapsed, 6),
                    "uds_request": result["uds_request"].hex().upper(),
                    "uds_response_prefix": result["uds_response"][:8].hex().upper(),
                })

    if traffic_pattern == "round_robin":
        sock = connect_with_retry(first_hop, port)
        activate(sock)
        with sock:
            for seq in range(samples):
                server_index = seq % 4
                service = service_for(seq, j1979_service)
                record(one_request(sock, targets[server_index], service, seq, name), server_index + 1)
    else:
        sockets = []
        try:
            for _ in range(4):
                sock = connect_with_retry(first_hop, port)
                activate(sock)
                sockets.append(sock)
            for base in range(0, samples, 4):
                futures = {}
                with ThreadPoolExecutor(max_workers=4) as pool:
                    for offset in range(4):
                        seq = base + offset
                        if seq >= samples:
                            break
                        service = service_for(seq, j1979_service)
                        future = pool.submit(one_request, sockets[offset], targets[offset], service, seq, name)
                        futures[future] = offset + 1
                    for future in as_completed(futures):
                        record(future.result(), futures[future])
        finally:
            for sock in sockets:
                sock.close()

    elapsed_values.sort()
    trace.sort(key=lambda item: item["sequence"])
    misses = sum(value > budget_ms for value in elapsed_values)
    per_server = {key: summary(values) for key, values in target_samples.items() if values}
    per_service = {key: summary(values) for key, values in service_samples.items() if values}
    return {
        "architecture": name,
        "label": LABELS[name],
        "samples": samples,
        "j1979_service": j1979_service,
        "j1979_service_label": SERVICE_LABELS[j1979_service],
        "traffic_pattern": traffic_pattern,
        "p2tester_budget_ms": budget_ms,
        "p2tester_elapsed_ms": summary(elapsed_values),
        "budget_miss_count": misses,
        "budget_miss_pct": round(100.0 * misses / samples, 6),
        "meets_99_percent": percentile(elapsed_values, 0.99) <= budget_ms,
        "histogram": histogram(elapsed_values, budget_ms),
        "per_server_p2tester_ms": per_server,
        "per_service_p2tester_ms": per_service,
        "trace": trace,
        "server_processing_ms": {"mean": None, "p50": None, "p95": None, "p99": None, "max": None},
        "architecture_delay_ms": {"mean": None, "p50": None, "p95": None, "p99": None, "max": None, "mean_components": {"end_to_end_only": None}},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--architecture", choices=("all", *LABELS.keys()), default="all")
    parser.add_argument("--legacy-gateway-ip", required=True)
    parser.add_argument("--hpc-ip", required=True)
    parser.add_argument("--port", type=int, default=13400)
    parser.add_argument("--samples", type=int, default=500)
    parser.add_argument("--budget-ms", type=float, default=50.0)
    parser.add_argument("--j1979-service", choices=tuple(SERVICE_LABELS), default="mixed")
    parser.add_argument("--traffic-pattern", choices=("round_robin", "parallel4"), default="round_robin")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    if not 12 <= args.samples <= 20_000:
        raise SystemExit("--samples must be between 12 and 20000")
    if args.budget_ms <= 0:
        raise SystemExit("--budget-ms must be positive")

    names = list(LABELS) if args.architecture == "all" else [args.architecture]
    results = []
    for name in names:
        first_hop = args.legacy_gateway_ip if name == "distributed_canfd" else args.hpc_ip
        results.append(run_architecture(name, first_hop, args.port, args.samples, args.budget_ms, args.j1979_service, args.traffic_pattern))

    payload = {
        "study": "Measured AWS SAE J1979-2 service-level architecture benchmark",
        "mode": "measured_aws_vehicle_architecture",
        "transport": "DoIP diagnostic-message framing over persistent TCP/IPv4 on private AWS VPC networking",
        "j1979_2_service_mode": args.j1979_service,
        "traffic_pattern": args.traffic_pattern,
        "protocol_note": "Research harness exercises UDS service patterns used by SAE J1979-2 (0x22, 0x19, 0x14, 0x31) inside DoIP diagnostic-message frames. Synthetic lab DIDs/DTCs/routine values are used; this is not a complete ISO 13400, ISO 14229, SAE J1979-2, or J1979DA conformance implementation.",
        "timing_note": "P2Tester is measured end-to-end only on the tester monotonic clock; no cross-host clock subtraction is used.",
        "topology": {
            "legacy": "Tester -> central gateway -> CAN-FD Bus A/B/C -> four distributed ECU diagnostic servers",
            "zonal_proxy": "Tester -> Graviton HPC application proxy -> four ZCU diagnostic servers",
        },
        "results": results,
    }
    Path(args.output).write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
