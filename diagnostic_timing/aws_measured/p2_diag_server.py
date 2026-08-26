#!/usr/bin/env python3
"""Measured diagnostic responder used for both legacy ECUs and zonal ZCUs."""
from __future__ import annotations

import argparse
import random
import socket
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
    parser.add_argument("--seed", type=int, default=1701)
    parser.add_argument("--idle-timeout-s", type=float, default=120.0)
    args = parser.parse_args()

    if args.min_ms < 0 or args.max_ms < args.min_ms or args.sigma_ms < 0:
        raise SystemExit("invalid diagnostic-server timing parameters")

    counters: dict[int, int] = {}
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((args.host, args.port))
    server.listen(16)
    server.settimeout(args.idle_timeout_s)
    print(
        f"{args.role} {args.zone_id} DoIP responder listening on {args.host}:{args.port} "
        f"logical=0x{args.logical_address:04X}", flush=True
    )

    try:
        while True:
            try:
                conn, peer = server.accept()
            except socket.timeout:
                print(f"{args.role} {args.zone_id} idle timeout", flush=True)
                break
            conn.settimeout(30.0)
            print(f"{args.role} {args.zone_id} accepted {peer[0]}:{peer[1]}", flush=True)
            with conn:
                while True:
                    try:
                        payload_type, payload = recv_frame(conn)
                    except (ConnectionError, socket.timeout):
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

                    request_index = counters.get(source, 0)
                    counters[source] = request_index + 1
                    sample_rng = random.Random(args.seed + args.zone_id * 100_000 + request_index)
                    configured_delay_ms = clamp(
                        sample_rng.gauss(args.mean_ms, args.sigma_ms), args.min_ms, args.max_ms
                    )
                    processing_start = time.perf_counter_ns()
                    if configured_delay_ms:
                        time.sleep(configured_delay_ms / 1000.0)

                    if len(uds) >= 3 and uds[0] == 0x22:
                        did = uds[1:3]
                        identity = f"{args.role.upper()}-{args.zone_id}".encode("ascii")
                        response_uds = b"\x62" + did + identity
                    elif uds and uds[0] == 0x3E:
                        response_uds = b"\x7E" + uds[1:2]
                    else:
                        sid = uds[0] if uds else 0x00
                        response_uds = bytes((0x7F, sid, 0x11))

                    processing_ms = (time.perf_counter_ns() - processing_start) / 1_000_000.0
                    print(
                        f"{args.role}={args.zone_id} source=0x{source:04X} target=0x{target:04X} "
                        f"request={request_index} configured_ms={configured_delay_ms:.3f} "
                        f"actual_ms={processing_ms:.3f}", flush=True
                    )
                    conn.sendall(diagnostic_message(args.logical_address, source, response_uds))
    finally:
        server.close()


if __name__ == "__main__":
    main()
