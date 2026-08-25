#!/usr/bin/env python3
"""External tester process for measured AWS P2Tester experiments."""
from __future__ import annotations

import argparse
import json
import math
import socket
import statistics
import time
from pathlib import Path

LABELS = {
    "distributed_canfd": "Distributed gateway path (Tester → Zone → Target)",
    "zonal_transparent": "Zonal transparent path (Tester → HPC → Zone → Target)",
    "zonal_hpc_proxy": "Zonal HPC diagnostic proxy (Tester → HPC → Zone → Target)",
}


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
        idx = min(bins - 1, int(value / width))
        counts[idx] += 1
    return [
        {"from_ms": round(i * width, 6), "to_ms": round((i + 1) * width, 6), "count": count}
        for i, count in enumerate(counts)
    ]


def connect_with_retry(host: str, port: int, timeout_s: float = 30.0) -> socket.socket:
    deadline = time.monotonic() + timeout_s
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(15.0)
        try:
            sock.connect((host, port))
            return sock
        except OSError as exc:
            last_error = exc
            sock.close()
            time.sleep(0.2)
    raise RuntimeError(f"cannot connect to {host}:{port}: {last_error}")


def run_architecture(name: str, first_hop: str, port: int, samples: int, budget_ms: float) -> dict:
    elapsed_values: list[float] = []
    target_values: list[float] = []
    zone_values: list[float] = []
    hpc_values: list[float] = []
    residual_values: list[float] = []
    trace: list[dict] = []

    sock = connect_with_retry(first_hop, port)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    with sock, sock.makefile("rwb") as stream:
        for seq in range(samples):
            request = {
                "type": "diagnostic_request",
                "sequence": seq,
                "architecture": name,
                "service": "0x22",
                "did": "F190",
                "tester_send_wall_ns": time.time_ns(),
            }
            payload = (json.dumps(request, separators=(",", ":")) + "\n").encode("utf-8")
            start_ns = time.perf_counter_ns()
            stream.write(payload)
            stream.flush()
            response_line = stream.readline()
            elapsed_ms = (time.perf_counter_ns() - start_ns) / 1_000_000.0
            if not response_line:
                raise RuntimeError(f"{name}: connection closed at sequence {seq}")
            response = json.loads(response_line)
            if response.get("sequence") != seq:
                raise RuntimeError(f"{name}: sequence mismatch {response.get('sequence')} != {seq}")

            target_ms = float(response.get("target_processing_ms", 0.0))
            zone_ms = float(response.get("zone_request_processing_ms", 0.0)) + float(
                response.get("zone_response_processing_ms", 0.0)
            )
            hpc_ms = float(response.get("hpc_request_processing_ms", 0.0)) + float(
                response.get("hpc_response_processing_ms", 0.0)
            )
            residual_ms = max(0.0, elapsed_ms - target_ms - zone_ms - hpc_ms)

            elapsed_values.append(elapsed_ms)
            target_values.append(target_ms)
            zone_values.append(zone_ms)
            hpc_values.append(hpc_ms)
            residual_values.append(residual_ms)
            if len(trace) < 200:
                trace.append({
                    "sequence": seq,
                    "p2tester_ms": round(elapsed_ms, 6),
                    "target_processing_ms": round(target_ms, 6),
                    "zone_local_ms": round(zone_ms, 6),
                    "hpc_local_ms": round(hpc_ms, 6),
                    "network_os_residual_ms": round(residual_ms, 6),
                    "tester_send_wall_ns": request["tester_send_wall_ns"],
                    "target_received_wall_ns": response.get("target_received_wall_ns"),
                    "target_response_wall_ns": response.get("target_response_wall_ns"),
                    "zone_received_wall_ns": response.get("zone_received_wall_ns"),
                    "zone_response_wall_ns": response.get("zone_response_wall_ns"),
                    "hpc_received_wall_ns": response.get("hpc_received_wall_ns"),
                    "hpc_response_wall_ns": response.get("hpc_response_wall_ns"),
                })

    architecture_overhead = [max(0.0, e - t) for e, t in zip(elapsed_values, target_values)]
    misses = sum(value > budget_ms for value in elapsed_values)
    components = {
        "zone_local_processing": round(statistics.fmean(zone_values), 6),
        "network_os_residual": round(statistics.fmean(residual_values), 6),
    }
    if name != "distributed_canfd":
        components["hpc_local_processing"] = round(statistics.fmean(hpc_values), 6)

    return {
        "architecture": name,
        "label": LABELS[name],
        "samples": samples,
        "p2tester_budget_ms": budget_ms,
        "server_processing_ms": summary(target_values),
        "architecture_delay_ms": {
            **summary(architecture_overhead),
            "mean_components": components,
        },
        "p2tester_elapsed_ms": summary(elapsed_values),
        "budget_miss_count": misses,
        "budget_miss_pct": round(100.0 * misses / samples, 6),
        "meets_99_percent": percentile(elapsed_values, 0.99) <= budget_ms,
        "histogram": histogram(elapsed_values, budget_ms),
        "measured_breakdown_ms": {
            "target_processing": summary(target_values),
            "zone_local_processing": summary(zone_values),
            "hpc_local_processing": summary(hpc_values),
            "network_os_residual": summary(residual_values),
        },
        "trace": trace,
    }


def shutdown_chain(hpc_ip: str, port: int) -> None:
    try:
        sock = connect_with_retry(hpc_ip, port, timeout_s=5.0)
        with sock, sock.makefile("rwb") as stream:
            stream.write((json.dumps({
                "type": "shutdown",
                "architecture": "zonal_transparent",
                "sequence": -1,
            }) + "\n").encode("utf-8"))
            stream.flush()
            stream.readline()
    except Exception as exc:
        print(f"warning: measured chain shutdown failed: {exc}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--architecture", choices=("all", *LABELS.keys()), default="all")
    parser.add_argument("--hpc-ip", required=True)
    parser.add_argument("--zone-ip", required=True)
    parser.add_argument("--port", type=int, default=13400)
    parser.add_argument("--samples", type=int, default=500)
    parser.add_argument("--budget-ms", type=float, default=50.0)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    if not 10 <= args.samples <= 5000:
        raise SystemExit("--samples must be between 10 and 5000")
    if args.budget_ms <= 0:
        raise SystemExit("--budget-ms must be positive")

    names = list(LABELS) if args.architecture == "all" else [args.architecture]
    results = []
    try:
        for name in names:
            first_hop = args.zone_ip if name == "distributed_canfd" else args.hpc_ip
            results.append(run_architecture(name, first_hop, args.port, args.samples, args.budget_ms))
    finally:
        shutdown_chain(args.hpc_ip, args.port)

    payload = {
        "study": "Measured AWS VPC OBDonUDS-style P2Tester architecture experiment",
        "mode": "measured_aws_vpc",
        "transport": "persistent TCP/IPv4 over private AWS VPC networking",
        "protocol_note": "UDS-style diagnostic framing for timing research; not a complete ISO 13400 DoIP implementation.",
        "timing_note": "P2Tester is measured end-to-end on the tester monotonic clock. Per-node local processing uses each node's monotonic clock; wall timestamps are observational only and are not subtracted across hosts.",
        "results": results,
    }
    Path(args.output).write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
