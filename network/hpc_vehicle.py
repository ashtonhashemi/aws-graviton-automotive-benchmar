#!/usr/bin/env python3
"""Graviton HPC vehicle/FMVSS 126-inspired SIL client using real UDP/IP.

The Graviton node runs the maneuver and vehicle plant. Every 10 ms it sends the
current sensor state to the x86 ZCU over the AWS VPC and applies the returned
ESC yaw-moment command to the next vehicle-dynamics step.
"""
from __future__ import annotations

import argparse
import json
import math
import platform
import socket
import statistics
import struct
import time
from pathlib import Path

DT = 0.01
ENTRY_SPEED_KPH = 80.0
ENTRY_SPEED_MPS = ENTRY_SPEED_KPH / 3.6
STEER_FREQUENCY_HZ = 0.7
DWELL_SECONDS = 0.5
STEERING_RATIO = 15.0
G = 9.81
MASS_KG = 1800.0
IZ_KGM2 = 3200.0
LF_M = 1.2
LR_M = 1.6
WHEELBASE_M = LF_M + LR_M
CF_N_PER_RAD = 80000.0
CR_N_PER_RAD = 30000.0
FRONT_FORCE_LIMIT_N = 6500.0
REAR_FORCE_LIMIT_N = 4500.0
SENSOR = struct.Struct("!Idfffff")
COMMAND = struct.Struct("!Iff")
STOP_SEQUENCE = 0xFFFFFFFF


def clamp(value: float, lo: float, hi: float) -> float:
    return lo if value < lo else hi if value > hi else value


def delta_03g_sw_deg() -> float:
    road_wheel_rad = (0.3 * G * WHEELBASE_M) / (ENTRY_SPEED_MPS ** 2)
    return math.degrees(road_wheel_rad) * STEERING_RATIO


def steer_input(t: float, amplitude_sw_deg: float, bos: float = 1.0) -> float:
    period = 1.0 / STEER_FREQUENCY_HZ
    quarter = period / 4.0
    u = t - bos
    if u < 0.0:
        return 0.0
    if u < 3.0 * quarter:
        return amplitude_sw_deg * math.sin(2.0 * math.pi * STEER_FREQUENCY_HZ * u)
    if u < 3.0 * quarter + DWELL_SECONDS:
        return -amplitude_sw_deg
    u -= DWELL_SECONDS
    if u < period:
        return amplitude_sw_deg * math.sin(2.0 * math.pi * STEER_FREQUENCY_HZ * u)
    return 0.0


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, math.ceil(len(ordered) * q) - 1))]


def run_once(zcu_ip: str, port: int, esc: str, timeout_ms: float, realtime: bool) -> dict:
    bos = 1.0
    cos = bos + (1.0 / STEER_FREQUENCY_HZ) + DWELL_SECONDS
    end_time = cos + 1.75 + 0.35
    amplitude = 5.0 * delta_03g_sw_deg()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout_ms / 1000.0)
    target = (zcu_ip, port)

    vy = yaw_rate = psi = lateral_position = ay = 0.0
    last_moment = 0.0
    samples = []
    rtt_ms: list[float] = []
    zcu_processing_us: list[float] = []
    packets_sent = packets_received = deadline_misses = 0
    seq = 0
    t = 0.0
    run_start = time.perf_counter()
    next_deadline = run_start

    while t <= end_time + 1e-9:
        steer_sw = steer_input(t, amplitude)
        speed_kph = ENTRY_SPEED_KPH
        beta = math.atan2(vy, ENTRY_SPEED_MPS)
        sent_ns = time.perf_counter_ns()
        payload = SENSOR.pack(
            seq,
            sent_ns,
            float(steer_sw),
            float(speed_kph),
            float(math.degrees(yaw_rate)),
            float(ay),
            float(beta),
        )

        packets_sent += 1
        try:
            sock.sendto(payload, target)
            response, _peer = sock.recvfrom(128)
            recv_ns = time.perf_counter_ns()
            rseq, moment, processing_us = COMMAND.unpack(response)
            if rseq == seq:
                last_moment = float(moment) if esc == "on" else 0.0
                packets_received += 1
                rtt = (recv_ns - sent_ns) / 1_000_000.0
                rtt_ms.append(rtt)
                zcu_processing_us.append(float(processing_us))
                if rtt > DT * 1000.0:
                    deadline_misses += 1
        except socket.timeout:
            deadline_misses += 1

        steer_road_rad = math.radians(steer_sw / STEERING_RATIO)
        vx = ENTRY_SPEED_MPS
        alpha_f = steer_road_rad - (vy + LF_M * yaw_rate) / vx
        alpha_r = -(vy - LR_M * yaw_rate) / vx
        fyf = clamp(CF_N_PER_RAD * alpha_f, -FRONT_FORCE_LIMIT_N, FRONT_FORCE_LIMIT_N)
        fyr = clamp(CR_N_PER_RAD * alpha_r, -REAR_FORCE_LIMIT_N, REAR_FORCE_LIMIT_N)
        vy_dot = (fyf + fyr) / MASS_KG - vx * yaw_rate
        yaw_dot = (LF_M * fyf - LR_M * fyr + last_moment) / IZ_KGM2
        vy += vy_dot * DT
        yaw_rate += yaw_dot * DT
        psi += yaw_rate * DT
        lateral_position += (vx * math.sin(psi) + vy * math.cos(psi)) * DT
        ay = vy_dot + vx * yaw_rate

        samples.append({
            "t_s": round(t, 3),
            "steer_sw_deg": round(steer_sw, 3),
            "yaw_rate_dps": round(math.degrees(yaw_rate), 3),
            "lateral_accel_mps2": round(ay, 4),
            "lateral_displacement_m": round(lateral_position, 4),
            "esc_yaw_moment_nm": round(last_moment, 2),
            "network_rtt_ms": round(rtt_ms[-1], 4) if rtt_ms else None,
        })

        seq += 1
        t += DT
        if realtime:
            next_deadline += DT
            sleep_s = next_deadline - time.perf_counter()
            if sleep_s > 0:
                time.sleep(sleep_s)

    try:
        sock.sendto(SENSOR.pack(STOP_SEQUENCE, time.perf_counter_ns(), 0.0, 0.0, 0.0, 0.0, 0.0), target)
    finally:
        sock.close()

    sign_change = bos + 1.0 / (2.0 * STEER_FREQUENCY_HZ)
    relevant = [s for s in samples if sign_change <= s["t_s"] <= cos]
    peak_yaw = max(abs(s["yaw_rate_dps"]) for s in relevant)

    def nearest(ts: float, key: str) -> float:
        return min(samples, key=lambda s: abs(s["t_s"] - ts))[key]

    yaw_1 = abs(nearest(cos + 1.0, "yaw_rate_dps"))
    yaw_175 = abs(nearest(cos + 1.75, "yaw_rate_dps"))
    ratio_1 = yaw_1 / peak_yaw if peak_yaw else 0.0
    ratio_175 = yaw_175 / peak_yaw if peak_yaw else 0.0
    displacement = abs(nearest(bos + 1.07, "lateral_displacement_m") - nearest(bos, "lateral_displacement_m"))

    p95 = percentile(rtt_ms, 0.95)
    return {
        "role": "AWS Graviton HPC / vehicle dynamics and maneuver simulator",
        "zcu_role": "x86 EC2 ZCU / ESC controller",
        "transport": "real bidirectional UDP/IPv4 over AWS VPC Ethernet",
        "zcu_private_ip": zcu_ip,
        "udp_port": port,
        "esc": esc,
        "entry_speed_kph": ENTRY_SPEED_KPH,
        "steer_frequency_hz": STEER_FREQUENCY_HZ,
        "dwell_seconds": DWELL_SECONDS,
        "sample_period_ms": int(DT * 1000),
        "scenario_steps": len(samples),
        "packets_sent": packets_sent,
        "packets_received": packets_received,
        "packets_lost": packets_sent - packets_received,
        "packet_loss_pct": round((packets_sent - packets_received) * 100.0 / packets_sent, 3),
        "control_deadline_misses": deadline_misses,
        "network_rtt_ms_mean": round(statistics.fmean(rtt_ms), 4) if rtt_ms else None,
        "network_rtt_ms_p95": round(p95, 4) if p95 is not None else None,
        "network_rtt_ms_max": round(max(rtt_ms), 4) if rtt_ms else None,
        "zcu_processing_us_mean": round(statistics.fmean(zcu_processing_us), 3) if zcu_processing_us else None,
        "peak_yaw_rate_dps": round(peak_yaw, 3),
        "yaw_ratio_1s_pct": round(ratio_1 * 100.0, 2),
        "yaw_ratio_1_75s_pct": round(ratio_175 * 100.0, 2),
        "lateral_displacement_1_07s_m": round(displacement, 3),
        "stability_1s_pass": ratio_1 < 0.35,
        "stability_1_75s_pass": ratio_175 < 0.20,
        "responsiveness_pass": displacement >= 1.83,
        "simulated_fmvss126_pass": ratio_1 < 0.35 and ratio_175 < 0.20 and displacement >= 1.83,
        "elapsed_wall_seconds": round(time.perf_counter() - run_start, 4),
        "hpc_architecture": platform.machine(),
        "trace": samples,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zcu-ip", required=True)
    parser.add_argument("--port", type=int, default=5005)
    parser.add_argument("--esc", choices=("on", "off"), default="on")
    parser.add_argument("--timeout-ms", type=float, default=20.0)
    parser.add_argument("--realtime", action="store_true")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    result = run_once(args.zcu_ip, args.port, args.esc, args.timeout_ms, args.realtime)
    Path(args.output).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "trace"}, indent=2))


if __name__ == "__main__":
    main()
