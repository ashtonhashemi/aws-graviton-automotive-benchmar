#!/usr/bin/env python3
"""x86 EC2 ZCU/ESC controller for the distributed ESC SIL lab.

Receives vehicle sensor frames over real UDP/IP from the Graviton HPC and returns
an ESC corrective yaw-moment command. This is an illustrative controller, not
production ESC software or a certification implementation.
"""
from __future__ import annotations

import argparse
import json
import math
import socket
import statistics
import struct
import time
from pathlib import Path

SENSOR = struct.Struct("!Idfffff")
COMMAND = struct.Struct("!Iff")
STOP_SEQUENCE = 0xFFFFFFFF
WHEELBASE_M = 2.8
ESC_YAW_GAIN = 40000.0
ESC_BETA_GAIN = 20000.0
ESC_MOMENT_LIMIT_NM = 6000.0


def clamp(value: float, lo: float, hi: float) -> float:
    return lo if value < lo else hi if value > hi else value


def control(steer_sw_deg: float, speed_kph: float, yaw_dps: float, beta_rad: float, enabled: bool) -> float:
    if not enabled:
        return 0.0
    speed_mps = max(speed_kph / 3.6, 0.1)
    road_wheel_rad = math.radians(steer_sw_deg / 15.0)
    desired_yaw = speed_mps / WHEELBASE_M * road_wheel_rad
    measured_yaw = math.radians(yaw_dps)
    return clamp(
        ESC_YAW_GAIN * (desired_yaw - measured_yaw) - ESC_BETA_GAIN * beta_rad,
        -ESC_MOMENT_LIMIT_NM,
        ESC_MOMENT_LIMIT_NM,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=5005)
    parser.add_argument("--esc", choices=("on", "off"), default="on")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((args.bind, args.port))
    sock.settimeout(args.timeout)

    packet_count = 0
    sequence_gaps = 0
    previous_sequence = None
    processing_us: list[float] = []
    source_ip = None
    started = time.time()
    stop_reason = "timeout"

    try:
        while True:
            try:
                payload, peer = sock.recvfrom(256)
            except socket.timeout:
                break
            if len(payload) != SENSOR.size:
                continue

            sequence, sent_ns, steer_sw_deg, speed_kph, yaw_dps, ay_mps2, beta_rad = SENSOR.unpack(payload)
            source_ip = peer[0]
            if sequence == STOP_SEQUENCE:
                stop_reason = "hpc_stop_frame"
                break

            t0 = time.perf_counter_ns()
            moment = control(steer_sw_deg, speed_kph, yaw_dps, beta_rad, args.esc == "on")
            elapsed_us = (time.perf_counter_ns() - t0) / 1000.0
            sock.sendto(COMMAND.pack(sequence, float(moment), float(elapsed_us)), peer)

            if previous_sequence is not None and sequence != previous_sequence + 1:
                sequence_gaps += max(0, sequence - previous_sequence - 1)
            previous_sequence = sequence
            packet_count += 1
            processing_us.append(elapsed_us)
    finally:
        sock.close()

    summary = {
        "role": "x86 EC2 ZCU / ESC controller",
        "transport": "real UDP/IPv4 over AWS VPC Ethernet",
        "listen_port": args.port,
        "esc": args.esc,
        "hpc_source_private_ip": source_ip,
        "packets_received": packet_count,
        "sequence_gaps": sequence_gaps,
        "controller_processing_us_mean": round(statistics.fmean(processing_us), 3) if processing_us else None,
        "controller_processing_us_p95": round(sorted(processing_us)[max(0, math.ceil(len(processing_us) * 0.95) - 1)], 3) if processing_us else None,
        "controller_processing_us_max": round(max(processing_us), 3) if processing_us else None,
        "runtime_seconds": round(time.time() - started, 3),
        "stop_reason": stop_reason,
    }
    Path(args.output).write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
