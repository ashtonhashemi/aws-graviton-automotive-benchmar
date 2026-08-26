#!/usr/bin/env python3
"""Legacy gateway / zonal HPC router for the measured P2Tester benchmark.

Legacy mode models three independent CAN-FD buses behind one central gateway:
Bus A -> ECU 1/2, Bus B -> ECU 3, Bus C -> ECU 4. HPC mode uses real AWS VPC
TCP plus a controlled automotive-Ethernet serialization/load emulator. Both
roles support synthetic CPU pressure for systems trade studies.
"""
from __future__ import annotations

import argparse
import multiprocessing as mp
import os
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
    routing_activation_request,
    routing_activation_response,
)

HPC_INTERNAL_SOURCE = 0x0A00
LEGACY_BUS_BY_TARGET = {
    0x1001: "A",
    0x1002: "A",
    0x1003: "B",
    0x1004: "C",
}


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
    """Approximate CAN-FD serialization + contention delay for timing research."""
    payload_bytes = max(1, payload_bytes)
    arb_control_bits = 58.0
    data_crc_bits = payload_bytes * 8.0 * 1.12 + 25.0
    serialization_s = arb_control_bits / arb_bps + data_crc_bits / data_bps
    contention_multiplier = 1.0 / max(0.05, 1.0 - bus_load)
    return serialization_s * contention_multiplier * 1000.0


def ethernet_delay_ms(payload_bytes: int, rate_mbps: float, link_load: float) -> float:
    """Controlled automotive-Ethernet serialization/queueing overlay.

    AWS VPC transport remains real. This adds only the chosen in-vehicle link
    characteristics so cloud network jitter is not mistaken for vehicle PHY behavior.
    """
    frame_bytes = max(64, payload_bytes + 42)  # Ethernet/IP/TCP/DoIP approximation
    serialization_s = frame_bytes * 8.0 / (rate_mbps * 1_000_000.0)
    contention_multiplier = 1.0 / max(0.05, 1.0 - link_load)
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
    parser.add_argument("--cpu-pressure-pct", type=float, default=0.0)
    parser.add_argument("--can-arb-bps", type=float, default=500_000.0)
    parser.add_argument("--can-data-bps", type=float, default=2_000_000.0)
    parser.add_argument("--can-load", type=float, default=None,
                        help="Legacy compatibility: override all three CAN bus loads")
    parser.add_argument("--can-load-a", type=float, default=0.30)
    parser.add_argument("--can-load-b", type=float, default=0.20)
    parser.add_argument("--can-load-c", type=float, default=0.10)
    parser.add_argument("--ethernet-rate-mbps", type=float, default=1000.0)
    parser.add_argument("--ethernet-load", type=float, default=0.20)
    parser.add_argument("--idle-timeout-s", type=float, default=120.0)
    args = parser.parse_args()

    if args.can_load is not None:
        args.can_load_a = args.can_load_b = args.can_load_c = args.can_load
    for value in (args.can_load_a, args.can_load_b, args.can_load_c, args.ethernet_load):
        if not 0 <= value < 0.95:
            raise SystemExit("network loads must be between 0 and 0.95")
    if args.proxy_work_ms < 0:
        raise SystemExit("--proxy-work-ms must be non-negative")
    if not 0 <= args.cpu_pressure_pct <= 95:
        raise SystemExit("--cpu-pressure-pct must be between 0 and 95")
    if args.ethernet_rate_mbps <= 0:
        raise SystemExit("--ethernet-rate-mbps must be positive")

    start_cpu_pressure(args.cpu_pressure_pct)
    routes = {logical: (host, port) for logical, host, port in map(parse_route, args.route)}
    proxy_routes = {
        alias: (actual, host, port)
        for alias, actual, host, port in map(parse_proxy_route, args.proxy_route)
    }
    if not routes and not proxy_routes:
        raise SystemExit("at least one --route or --proxy-route is required")

    bus_loads = {"A": args.can_load_a, "B": args.can_load_b, "C": args.can_load_c}

    def vehicle_link_delay(target: int, uds_len: int) -> None:
        if args.role == "legacy_gateway":
            bus = LEGACY_BUS_BY_TARGET.get(target, "A")
            delay = canfd_delay_ms(uds_len, args.can_arb_bps, args.can_data_bps, bus_loads[bus])
        else:
            delay = ethernet_delay_ms(uds_len, args.ethernet_rate_mbps, args.ethernet_load)
        if delay > 0:
            time.sleep(delay / 1000.0)

    def handle(upstream: socket.socket, peer) -> None:
        upstream.settimeout(30.0)
        upstream.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        print(f"{args.role} accepted tester {peer[0]}:{peer[1]}", flush=True)
        with upstream:
            while True:
                try:
                    payload_type, payload = recv_frame(upstream)
                except (ConnectionError, socket.timeout, OSError):
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

                vehicle_link_delay(actual_target if args.role == "hpc" else requested_target, len(uds))
                if proxy and args.proxy_work_ms:
                    time.sleep(args.proxy_work_ms / 1000.0)

                downstream = connect_downstream(host, port, downstream_source)
                with downstream:
                    downstream.sendall(diagnostic_message(downstream_source, actual_target, uds))
                    response_type, response_payload = recv_frame(downstream)
                    if response_type != PT_DIAGNOSTIC_MESSAGE:
                        raise RuntimeError("downstream did not return a DoIP diagnostic message")
                    response_source, _, response_uds = parse_diagnostic_message(response_payload)

                vehicle_link_delay(actual_target if args.role == "hpc" else requested_target, len(response_uds))
                tester_response_source = requested_target if proxy else response_source
                upstream.sendall(diagnostic_message(tester_response_source, tester_source, response_uds))

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((args.host, args.port))
    server.listen(64)
    server.settimeout(args.idle_timeout_s)
    print(
        f"{args.role} listening {args.host}:{args.port} cpu_pressure={args.cpu_pressure_pct:.1f}% "
        f"CAN[A/B/C]={args.can_load_a:.2f}/{args.can_load_b:.2f}/{args.can_load_c:.2f} "
        f"ETH={args.ethernet_rate_mbps:.0f}Mbps load={args.ethernet_load:.2f}",
        flush=True,
    )

    threads: list[threading.Thread] = []
    try:
        while True:
            try:
                upstream, peer = server.accept()
            except socket.timeout:
                print(f"{args.role} idle timeout", flush=True)
                break
            thread = threading.Thread(target=handle, args=(upstream, peer), daemon=True)
            thread.start()
            threads.append(thread)
    finally:
        server.close()
        for thread in threads:
            thread.join(timeout=2.0)


if __name__ == "__main__":
    main()
