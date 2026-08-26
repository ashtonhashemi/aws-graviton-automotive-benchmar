#!/usr/bin/env python3
"""Legacy gateway / zonal HPC router for the measured P2Tester benchmark.

Legacy mode applies an explicit CAN-FD timing model before forwarding a UDS
request to one of four distributed ECU responders. HPC mode transparently
routes requests to one of four ZCUs, or terminates and reissues the request for
proxy logical addresses.
"""
from __future__ import annotations

import argparse
import socket
import time

from doip_codec import (
    PT_DIAGNOSTIC_MESSAGE,
    PT_ROUTING_ACTIVATION_REQUEST,
    diagnostic_message,
    parse_diagnostic_message,
    parse_routing_activation_request,
    recv_frame,
    routing_activation_request,
    routing_activation_response,
)

HPC_INTERNAL_SOURCE = 0x0A00


def parse_int(value: str) -> int:
    return int(value, 0)


def parse_route(value: str) -> tuple[int, str, int]:
    logical, endpoint = value.split("=", 1)
    host, port = endpoint.rsplit(":", 1)
    return int(logical, 0), host, int(port)


def parse_proxy_route(value: str) -> tuple[int, int, str, int]:
    alias, downstream = value.split("=", 1)
    actual, endpoint = downstream.split("@", 1)
    host, port = endpoint.rsplit(":", 1)
    return int(alias, 0), int(actual, 0), host, int(port)


def connect_downstream(host: str, port: int, source_address: int, timeout_s: float = 20.0) -> socket.socket:
    deadline = time.monotonic() + timeout_s
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(15.0)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        try:
            sock.connect((host, port))
            sock.sendall(routing_activation_request(source_address))
            recv_frame(sock)
            return sock
        except Exception as exc:
            last_error = exc
            sock.close()
            time.sleep(0.2)
    raise RuntimeError(f"cannot connect downstream {host}:{port}: {last_error}")


def canfd_delay_ms(payload_bytes: int, arb_bps: float, data_bps: float, bus_load: float) -> float:
    """Approximate CAN-FD serialization + contention delay for timing research.

    This is deliberately labelled an emulator, not a physical CAN interface.
    Arbitration/control bits use the nominal rate; payload/CRC bits use the
    data-phase rate. A utilization multiplier approximates queueing pressure.
    """
    payload_bytes = max(1, payload_bytes)
    arb_control_bits = 58.0
    data_crc_bits = payload_bytes * 8.0 * 1.12 + 25.0
    serialization_s = arb_control_bits / arb_bps + data_crc_bits / data_bps
    contention_multiplier = 1.0 / max(0.05, 1.0 - bus_load)
    return serialization_s * contention_multiplier * 1000.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=("legacy_gateway", "hpc"), required=True)
    parser.add_argument("--entity-address", type=parse_int, required=True)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=13400)
    parser.add_argument("--route", action="append", default=[])
    parser.add_argument("--proxy-route", action="append", default=[])
    parser.add_argument("--proxy-work-ms", type=float, default=0.0)
    parser.add_argument("--can-arb-bps", type=float, default=500_000.0)
    parser.add_argument("--can-data-bps", type=float, default=2_000_000.0)
    parser.add_argument("--can-load", type=float, default=0.30)
    parser.add_argument("--idle-timeout-s", type=float, default=120.0)
    args = parser.parse_args()

    if not 0 <= args.can_load < 0.95:
        raise SystemExit("--can-load must be between 0 and 0.95")
    if args.proxy_work_ms < 0:
        raise SystemExit("--proxy-work-ms must be non-negative")

    routes = {logical: (host, port) for logical, host, port in map(parse_route, args.route)}
    proxy_routes = {
        alias: (actual, host, port)
        for alias, actual, host, port in map(parse_proxy_route, args.proxy_route)
    }
    if not routes and not proxy_routes:
        raise SystemExit("at least one --route or --proxy-route is required")

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((args.host, args.port))
    server.listen(32)
    server.settimeout(args.idle_timeout_s)
    print(f"{args.role} listening on {args.host}:{args.port}", flush=True)

    try:
        while True:
            try:
                upstream, peer = server.accept()
            except socket.timeout:
                print(f"{args.role} idle timeout", flush=True)
                break
            upstream.settimeout(30.0)
            upstream.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            print(f"{args.role} accepted tester {peer[0]}:{peer[1]}", flush=True)
            with upstream:
                while True:
                    try:
                        payload_type, payload = recv_frame(upstream)
                    except (ConnectionError, socket.timeout):
                        break

                    if payload_type == PT_ROUTING_ACTIVATION_REQUEST:
                        source, _ = parse_routing_activation_request(payload)
                        upstream.sendall(routing_activation_response(source, args.entity_address))
                        continue
                    if payload_type != PT_DIAGNOSTIC_MESSAGE:
                        continue

                    tester_source, requested_target, uds = parse_diagnostic_message(payload)
                    proxy = requested_target in proxy_routes
                    if proxy:
                        actual_target, host, port = proxy_routes[requested_target]
                        downstream_source = HPC_INTERNAL_SOURCE
                    elif requested_target in routes:
                        host, port = routes[requested_target]
                        actual_target = requested_target
                        downstream_source = tester_source
                    else:
                        continue

                    if args.role == "legacy_gateway":
                        delay = canfd_delay_ms(len(uds), args.can_arb_bps, args.can_data_bps, args.can_load)
                        time.sleep(delay / 1000.0)
                    if proxy and args.proxy_work_ms:
                        # Application-proxy overhead: parse/dispatch before creating a new
                        # downstream diagnostic transaction.
                        time.sleep(args.proxy_work_ms / 1000.0)

                    downstream = connect_downstream(host, port, downstream_source)
                    with downstream:
                        downstream.sendall(diagnostic_message(downstream_source, actual_target, uds))
                        response_type, response_payload = recv_frame(downstream)
                        if response_type != PT_DIAGNOSTIC_MESSAGE:
                            raise RuntimeError("downstream did not return a DoIP diagnostic message")
                        response_source, _, response_uds = parse_diagnostic_message(response_payload)

                    if args.role == "legacy_gateway":
                        delay = canfd_delay_ms(len(response_uds), args.can_arb_bps, args.can_data_bps, args.can_load)
                        time.sleep(delay / 1000.0)

                    # Transparent routes preserve the responder logical address. Proxy routes
                    # expose the tester-facing proxy alias because the HPC owns that endpoint.
                    tester_response_source = requested_target if proxy else response_source
                    upstream.sendall(diagnostic_message(tester_response_source, tester_source, response_uds))
    finally:
        server.close()


if __name__ == "__main__":
    main()
