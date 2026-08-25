#!/usr/bin/env python3
"""Target ECU simulator for the measured AWS P2Tester experiment.

The network path is real TCP/IPv4 over the AWS VPC. ECU processing time is a
controlled test stimulus so architecture/network overhead can be measured
separately from target-server work.
"""
from __future__ import annotations

import argparse
import json
import random
import socket
import time


def clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


def send_json(stream, payload: dict) -> None:
    stream.write((json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8"))
    stream.flush()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=13400)
    parser.add_argument("--mean-ms", type=float, default=20.0)
    parser.add_argument("--sigma-ms", type=float, default=7.0)
    parser.add_argument("--min-ms", type=float, default=3.0)
    parser.add_argument("--max-ms", type=float, default=45.0)
    parser.add_argument("--seed", type=int, default=1701)
    parser.add_argument("--idle-timeout-s", type=float, default=300.0)
    args = parser.parse_args()

    if args.min_ms < 0 or args.max_ms < args.min_ms or args.sigma_ms < 0:
        raise SystemExit("invalid target ECU timing parameters")

    rng = random.Random(args.seed)
    stop = False
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((args.host, args.port))
    server.listen(8)
    server.settimeout(args.idle_timeout_s)
    print(f"P2 target ECU listening on {args.host}:{args.port}", flush=True)

    try:
        while not stop:
            try:
                conn, peer = server.accept()
            except socket.timeout:
                print("target ECU idle timeout", flush=True)
                break
            print(f"target accepted {peer[0]}:{peer[1]}", flush=True)
            conn.settimeout(60.0)
            with conn, conn.makefile("rwb") as stream:
                while True:
                    line = stream.readline()
                    if not line:
                        break
                    request_received_wall_ns = time.time_ns()
                    request = json.loads(line)
                    if request.get("type") == "shutdown":
                        send_json(stream, {
                            "type": "shutdown_ack",
                            "target_received_wall_ns": request_received_wall_ns,
                            "target_response_wall_ns": time.time_ns(),
                        })
                        stop = True
                        break

                    processing_start_ns = time.perf_counter_ns()
                    configured_delay_ms = clamp(
                        rng.gauss(args.mean_ms, args.sigma_ms), args.min_ms, args.max_ms
                    )
                    if configured_delay_ms:
                        time.sleep(configured_delay_ms / 1000.0)
                    processing_ms = (time.perf_counter_ns() - processing_start_ns) / 1_000_000.0
                    response_wall_ns = time.time_ns()
                    send_json(stream, {
                        "type": "diagnostic_response",
                        "sequence": request.get("sequence"),
                        "architecture": request.get("architecture"),
                        "service": "0x62",
                        "did": request.get("did", "F190"),
                        "data": "SIMULATED-VIN-DATA",
                        "target_configured_delay_ms": round(configured_delay_ms, 6),
                        "target_processing_ms": round(processing_ms, 6),
                        "target_received_wall_ns": request_received_wall_ns,
                        "target_response_wall_ns": response_wall_ns,
                    })
    finally:
        server.close()


if __name__ == "__main__":
    main()
