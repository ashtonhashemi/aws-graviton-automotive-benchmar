#!/usr/bin/env python3
"""Measured diagnostic responder used for both legacy ECUs and zonal ZCUs.

Implements a service-level OBDonUDS research harness for the four UDS services
used by SAE J1979-2 mappings: 0x22, 0x19, 0x14, and 0x31. Payload data and
routine/DTC values are synthetic lab data; this is not a conformance server.
"""
from __future__ import annotations

import argparse
import multiprocessing as mp
import os
import random
import socket
import threading
import time

from doip_codec import (
    PT_DIAGNOSTIC_MESSAGE,
    PT_ROUTING_ACTIVATION_REQUEST,
    diagnostic_message,
    parse_diagnostic_message,
    parse_routing_activation_request,
    recv_frame,
    routing_activation_response,
)


def parse_int(value: str) -> int:
    return int(value, 0)


def clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


def _cpu_worker(duty: float, cpu: int | None) -> None:
    if cpu is not None:
        try:
            os.sched_setaffinity(0, {cpu})
        except (AttributeError, OSError):
            pass
    period = 0.010
    busy = period * duty
    while True:
        start = time.perf_counter()
        while time.perf_counter() - start < busy:
            pass
        remaining = period - (time.perf_counter() - start)
        if remaining > 0:
            time.sleep(remaining)


def start_cpu_pressure(percent: float) -> list[mp.Process]:
    if percent <= 0:
        return []
    duty = min(0.95, percent / 100.0)
    try:
        cpus = sorted(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        cpus = list(range(os.cpu_count() or 1))
    workers = []
    for cpu in cpus:
        proc = mp.Process(target=_cpu_worker, args=(duty, cpu), daemon=True)
        proc.start()
        workers.append(proc)
    return workers


def positive_response(uds: bytes, identity: bytes, dtc_state: dict[str, bool]) -> bytes:
    """Return synthetic positive UDS responses for the J1979-2 service set."""
    if not uds:
        return b"\x7F\x00\x13"
    sid = uds[0]
    if sid == 0x22 and len(uds) >= 3:  # ReadDataByIdentifier
        return b"\x62" + uds[1:3] + identity
    if sid == 0x19 and len(uds) >= 2:  # ReadDTCInformation
        sub = uds[1]
        # Synthetic lab record: status availability + one 3-byte DTC while active.
        record = b"\xFF\x01\x23\x45\x2F" if dtc_state["present"] else b"\xFF"
        return b"\x59" + bytes((sub,)) + record
    if sid == 0x14:  # ClearDiagnosticInformation
        dtc_state["present"] = False
        return b"\x54"
    if sid == 0x31 and len(uds) >= 4:  # RoutineControl
        return b"\x71" + uds[1:4] + b"\x00"
    if sid == 0x3E:
        return b"\x7E" + uds[1:2]
    return bytes((0x7F, sid, 0x11))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=("legacy_ecu", "zcu"), required=True)
    parser.add_argument("--zone-id", type=int, choices=(1, 2, 3, 4), required=True)
    parser.add_argument("--logical-address", type=parse_int, required=True)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=13400)
    parser.add_argument("--mean-ms", type=float, default=20.0)
    parser.add_argument("--sigma-ms", type=float, default=7.0)
    parser.add_argument("--min-ms", type=float, default=3.0)
    parser.add_argument("--max-ms", type=float, default=45.0)
    parser.add_argument("--cpu-pressure-pct", type=float, default=0.0)
    parser.add_argument("--seed", type=int, default=1701)
    parser.add_argument("--idle-timeout-s", type=float, default=120.0)
    args = parser.parse_args()

    if args.min_ms < 0 or args.max_ms < args.min_ms or args.sigma_ms < 0:
        raise SystemExit("invalid diagnostic-server timing parameters")
    if not 0 <= args.cpu_pressure_pct <= 95:
        raise SystemExit("--cpu-pressure-pct must be between 0 and 95")

    start_cpu_pressure(args.cpu_pressure_pct)
    counters: dict[int, int] = {}
    counters_lock = threading.Lock()
    dtc_state = {"present": True}
    dtc_lock = threading.Lock()
    identity = f"{args.role.upper()}-{args.zone_id}".encode("ascii")

    def handle(conn: socket.socket, peer) -> None:
        conn.settimeout(30.0)
        print(f"{args.role} {args.zone_id} accepted {peer[0]}:{peer[1]}", flush=True)
        with conn:
            while True:
                try:
                    payload_type, payload = recv_frame(conn)
                except (ConnectionError, socket.timeout, OSError):
                    break

                if payload_type == PT_ROUTING_ACTIVATION_REQUEST:
                    source, _ = parse_routing_activation_request(payload)
                    conn.sendall(routing_activation_response(source, args.logical_address))
                    continue
                if payload_type != PT_DIAGNOSTIC_MESSAGE:
                    continue

                source, target, uds = parse_diagnostic_message(payload)
                if target != args.logical_address:
                    continue

                with counters_lock:
                    request_index = counters.get(source, 0)
                    counters[source] = request_index + 1
                sample_rng = random.Random(args.seed + args.zone_id * 100_000 + request_index)
                configured_delay_ms = clamp(
                    sample_rng.gauss(args.mean_ms, args.sigma_ms), args.min_ms, args.max_ms
                )
                processing_start = time.perf_counter_ns()
                if configured_delay_ms:
                    time.sleep(configured_delay_ms / 1000.0)
                with dtc_lock:
                    response_uds = positive_response(uds, identity, dtc_state)
                processing_ms = (time.perf_counter_ns() - processing_start) / 1_000_000.0

                print(
                    f"{args.role}={args.zone_id} sid=0x{(uds[0] if uds else 0):02X} "
                    f"request={request_index} configured_ms={configured_delay_ms:.3f} actual_ms={processing_ms:.3f}",
                    flush=True,
                )
                conn.sendall(diagnostic_message(args.logical_address, source, response_uds))

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((args.host, args.port))
    server.listen(32)
    server.settimeout(args.idle_timeout_s)
    print(
        f"{args.role} {args.zone_id} DoIP responder listening on {args.host}:{args.port} "
        f"logical=0x{args.logical_address:04X} cpu_pressure={args.cpu_pressure_pct:.1f}%",
        flush=True,
    )

    threads: list[threading.Thread] = []
    try:
        while True:
            try:
                conn, peer = server.accept()
            except socket.timeout:
                print(f"{args.role} {args.zone_id} idle timeout", flush=True)
                break
            thread = threading.Thread(target=handle, args=(conn, peer), daemon=True)
            thread.start()
            threads.append(thread)
    finally:
        server.close()
        for thread in threads:
            thread.join(timeout=2.0)


if __name__ == "__main__":
    main()
