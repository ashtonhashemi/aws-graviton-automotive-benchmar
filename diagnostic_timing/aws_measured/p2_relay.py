#!/usr/bin/env python3
"""HPC/zone relay for measured OBDonUDS P2Tester architecture timing.

This is not a complete ISO 13400 DoIP stack. It uses persistent TCP sessions and
newline-delimited diagnostic messages to measure real AWS VPC transport plus
software forwarding/proxy overhead while preserving an explicit UDS-style
request/response flow.
"""
from __future__ import annotations

import argparse
import json
import socket
import time


def connect_with_retry(host: str, port: int, timeout_s: float = 30.0) -> socket.socket:
    deadline = time.monotonic() + timeout_s
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10.0)
        try:
            sock.connect((host, port))
            return sock
        except OSError as exc:
            last_error = exc
            sock.close()
            time.sleep(0.2)
    raise RuntimeError(f"cannot connect to downstream {host}:{port}: {last_error}")


def send_line(stream, payload: bytes) -> None:
    stream.write(payload if payload.endswith(b"\n") else payload + b"\n")
    stream.flush()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=("hpc", "zone"), required=True)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=13400)
    parser.add_argument("--downstream-host", required=True)
    parser.add_argument("--downstream-port", type=int, default=13400)
    parser.add_argument("--proxy-work-ms", type=float, default=0.0,
                        help="Controlled application-level work applied only by HPC proxy mode")
    parser.add_argument("--idle-timeout-s", type=float, default=300.0)
    args = parser.parse_args()

    if args.proxy_work_ms < 0:
        raise SystemExit("--proxy-work-ms must be >= 0")

    stop = False
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((args.host, args.port))
    server.listen(8)
    server.settimeout(args.idle_timeout_s)
    print(
        f"P2 {args.role} listening {args.host}:{args.port} -> "
        f"{args.downstream_host}:{args.downstream_port}", flush=True
    )

    try:
        while not stop:
            try:
                upstream, peer = server.accept()
            except socket.timeout:
                print(f"{args.role} idle timeout", flush=True)
                break
            print(f"{args.role} accepted {peer[0]}:{peer[1]}", flush=True)
            upstream.settimeout(60.0)
            try:
                downstream = connect_with_retry(args.downstream_host, args.downstream_port)
            except Exception:
                upstream.close()
                raise

            with upstream, downstream, upstream.makefile("rwb") as up, downstream.makefile("rwb") as down:
                while True:
                    request_line = up.readline()
                    if not request_line:
                        break
                    receive_wall_ns = time.time_ns()
                    local_start_ns = time.perf_counter_ns()
                    request = json.loads(request_line)
                    architecture = request.get("architecture", "")

                    if args.role == "hpc" and architecture == "zonal_hpc_proxy":
                        # Terminate, inspect and reissue the request. The optional delay is a
                        # controlled proxy-service workload, reported separately from network time.
                        reissued = dict(request)
                        reissued["hpc_proxy_reissued"] = True
                        reissued["hpc_proxy_received_wall_ns"] = receive_wall_ns
                        if args.proxy_work_ms:
                            time.sleep(args.proxy_work_ms / 1000.0)
                        outbound = (json.dumps(reissued, separators=(",", ":")) + "\n").encode("utf-8")
                    else:
                        outbound = request_line if request_line.endswith(b"\n") else request_line + b"\n"

                    request_local_ms = (time.perf_counter_ns() - local_start_ns) / 1_000_000.0
                    forward_wall_ns = time.time_ns()
                    send_line(down, outbound)
                    response_line = down.readline()
                    downstream_response_wall_ns = time.time_ns()
                    if not response_line:
                        raise RuntimeError(f"{args.role} downstream closed without response")

                    response_local_start_ns = time.perf_counter_ns()
                    response = json.loads(response_line)
                    response[f"{args.role}_request_processing_ms"] = round(request_local_ms, 6)
                    response[f"{args.role}_response_processing_ms"] = round(
                        (time.perf_counter_ns() - response_local_start_ns) / 1_000_000.0, 6
                    )
                    response[f"{args.role}_received_wall_ns"] = receive_wall_ns
                    response[f"{args.role}_forwarded_wall_ns"] = forward_wall_ns
                    response[f"{args.role}_downstream_response_wall_ns"] = downstream_response_wall_ns
                    response[f"{args.role}_response_wall_ns"] = time.time_ns()
                    response[f"{args.role}_proxy_work_ms"] = (
                        args.proxy_work_ms if args.role == "hpc" and architecture == "zonal_hpc_proxy" else 0.0
                    )
                    send_line(up, (json.dumps(response, separators=(",", ":")) + "\n").encode("utf-8"))

                    if request.get("type") == "shutdown":
                        stop = True
                        break
    finally:
        server.close()


if __name__ == "__main__":
    main()
