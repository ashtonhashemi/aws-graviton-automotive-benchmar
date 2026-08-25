#!/usr/bin/env python3
"""FMVSS 126-inspired ESC SIL workload for x86_64 vs AWS Graviton.

This is an engineering simulation/portfolio workload, not a compliance certification tool.
It models a 0.7 Hz sine-with-dwell steering input, CAN signal exchange, a closed-loop
ESC yaw controller, a simplified nonlinear bicycle plant, and Ethernet-style telemetry.
"""
from __future__ import annotations

import argparse
import json
import math
import platform
import resource
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

# Illustrative midsize vehicle / oversteer-prone plant.
MASS_KG = 1800.0
IZ_KGM2 = 3200.0
LF_M = 1.2
LR_M = 1.6
WHEELBASE_M = LF_M + LR_M
CF_N_PER_RAD = 80000.0
CR_N_PER_RAD = 30000.0
FRONT_FORCE_LIMIT_N = 6500.0
REAR_FORCE_LIMIT_N = 4500.0

ESC_YAW_GAIN = 40000.0
ESC_BETA_GAIN = 20000.0
ESC_MOMENT_LIMIT_NM = 6000.0

CAN_STRUCT = struct.Struct("<hHhh")
TELEM_STRUCT = struct.Struct("<Ifffff")


def clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def delta_03g_steering_wheel_deg() -> float:
    """Simplified SIS characterization: steering-wheel angle associated with 0.3 g."""
    road_wheel_rad = (0.3 * G * WHEELBASE_M) / (ENTRY_SPEED_MPS**2)
    return math.degrees(road_wheel_rad) * STEERING_RATIO


def sine_with_dwell_steering(t: float, amplitude_sw_deg: float, bos: float = 1.0) -> float:
    """0.7 Hz sine wave with a 500 ms dwell at the second peak."""
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


def can_roundtrip_baseline(steer_sw_deg: float, speed_kph: float, yaw_dps: float, ay: float) -> dict:
    payload = CAN_STRUCT.pack(
        int(round(clamp(steer_sw_deg * 10.0, -32768, 32767))),
        int(round(clamp(speed_kph * 10.0, 0, 65535))),
        int(round(clamp(yaw_dps * 100.0, -32768, 32767))),
        int(round(clamp(ay * 100.0, -32768, 32767))),
    )
    s, v, r, a = CAN_STRUCT.unpack(payload)
    return {"steer_sw_deg": s / 10.0, "speed_kph": v / 10.0, "yaw_dps": r / 100.0, "ay": a / 100.0}


def can_roundtrip_optimized(steer_sw_deg: float, speed_kph: float, yaw_dps: float, ay: float) -> tuple[float, float, float, float]:
    payload = CAN_STRUCT.pack(
        int(round(clamp(steer_sw_deg * 10.0, -32768, 32767))),
        int(round(clamp(speed_kph * 10.0, 0, 65535))),
        int(round(clamp(yaw_dps * 100.0, -32768, 32767))),
        int(round(clamp(ay * 100.0, -32768, 32767))),
    )
    s, v, r, a = CAN_STRUCT.unpack(payload)
    return s / 10.0, v / 10.0, r / 100.0, a / 100.0


def run_scenario(mode: str, esc: str) -> dict:
    bos = 1.0
    cos = bos + (1.0 / STEER_FREQUENCY_HZ) + DWELL_SECONDS
    end_time = cos + 1.75 + 0.35
    d03 = delta_03g_steering_wheel_deg()
    amplitude = 5.0 * d03

    vy = 0.0
    yaw_rate = 0.0
    psi = 0.0
    lateral_position = 0.0
    ay = 0.0

    samples: list[tuple[float, float, float, float, float, float]] = []
    telemetry_checksum = 0
    step = 0
    t = 0.0

    while t <= end_time + 1e-9:
        steer_cmd = sine_with_dwell_steering(t, amplitude)
        if mode == "optimized":
            steer_sw, speed_kph, measured_yaw_dps, measured_ay = can_roundtrip_optimized(
                steer_cmd, ENTRY_SPEED_KPH, math.degrees(yaw_rate), ay
            )
        else:
            sig = can_roundtrip_baseline(steer_cmd, ENTRY_SPEED_KPH, math.degrees(yaw_rate), ay)
            steer_sw = sig["steer_sw_deg"]
            speed_kph = sig["speed_kph"]
            measured_yaw_dps = sig["yaw_dps"]
            measured_ay = sig["ay"]

        vx = speed_kph / 3.6
        steer_road_rad = math.radians(steer_sw / STEERING_RATIO)
        measured_yaw = math.radians(measured_yaw_dps)
        beta = math.atan2(vy, max(vx, 0.1))
        desired_yaw = vx / WHEELBASE_M * steer_road_rad

        corrective_moment = 0.0
        if esc == "on":
            corrective_moment = clamp(
                ESC_YAW_GAIN * (desired_yaw - measured_yaw) - ESC_BETA_GAIN * beta,
                -ESC_MOMENT_LIMIT_NM,
                ESC_MOMENT_LIMIT_NM,
            )

        alpha_f = steer_road_rad - (vy + LF_M * yaw_rate) / vx
        alpha_r = -(vy - LR_M * yaw_rate) / vx
        fyf = clamp(CF_N_PER_RAD * alpha_f, -FRONT_FORCE_LIMIT_N, FRONT_FORCE_LIMIT_N)
        fyr = clamp(CR_N_PER_RAD * alpha_r, -REAR_FORCE_LIMIT_N, REAR_FORCE_LIMIT_N)

        vy_dot = (fyf + fyr) / MASS_KG - vx * yaw_rate
        yaw_dot = (LF_M * fyf - LR_M * fyr + corrective_moment) / IZ_KGM2

        vy += vy_dot * DT
        yaw_rate += yaw_dot * DT
        psi += yaw_rate * DT
        lateral_position += (vx * math.sin(psi) + vy * math.cos(psi)) * DT
        ay = vy_dot + vx * yaw_rate

        # Ethernet-style telemetry packet at 10 Hz.
        if step % 10 == 0:
            packet = TELEM_STRUCT.pack(
                step,
                float(steer_sw),
                float(math.degrees(yaw_rate)),
                float(ay),
                float(lateral_position),
                float(corrective_moment),
            )
            telemetry_checksum = (telemetry_checksum + sum(packet)) & 0xFFFFFFFF

        samples.append((t, steer_sw, yaw_rate, ay, lateral_position, corrective_moment))
        step += 1
        t += DT

    sign_change = bos + 1.0 / (2.0 * STEER_FREQUENCY_HZ)
    peak_yaw = max(abs(s[2]) for s in samples if sign_change <= s[0] <= cos)

    def nearest(ts: float, index: int) -> float:
        return min(samples, key=lambda s: abs(s[0] - ts))[index]

    yaw_1s = abs(nearest(cos + 1.0, 2))
    yaw_175s = abs(nearest(cos + 1.75, 2))
    yaw_ratio_1s = yaw_1s / peak_yaw if peak_yaw else 0.0
    yaw_ratio_175s = yaw_175s / peak_yaw if peak_yaw else 0.0
    displacement = abs(nearest(bos + 1.07, 4) - nearest(bos, 4))

    stability_1s_pass = yaw_ratio_1s < 0.35
    stability_175s_pass = yaw_ratio_175s < 0.20
    responsiveness_pass = displacement >= 1.83

    return {
        "test": "FMVSS 126-inspired Sine with Dwell SIL",
        "esc": esc,
        "entry_speed_kph": ENTRY_SPEED_KPH,
        "steer_frequency_hz": STEER_FREQUENCY_HZ,
        "dwell_seconds": DWELL_SECONDS,
        "delta_0_3g_sw_deg": round(d03, 3),
        "steering_amplitude_sw_deg": round(amplitude, 3),
        "sample_period_ms": int(DT * 1000),
        "scenario_steps": len(samples),
        "can_transport": "simulated CAN sensor/control frames",
        "ethernet_transport": "simulated binary telemetry packet every 100 ms",
        "peak_yaw_rate_dps": round(math.degrees(peak_yaw), 3),
        "yaw_ratio_1s_pct": round(yaw_ratio_1s * 100.0, 2),
        "yaw_ratio_1_75s_pct": round(yaw_ratio_175s * 100.0, 2),
        "lateral_displacement_1_07s_m": round(displacement, 3),
        "stability_1s_pass": stability_1s_pass,
        "stability_1_75s_pass": stability_175s_pass,
        "responsiveness_pass": responsiveness_pass,
        "simulated_fmvss126_pass": stability_1s_pass and stability_175s_pass and responsiveness_pass,
        "max_corrective_yaw_moment_nm": round(max(abs(s[5]) for s in samples), 1),
        "telemetry_checksum": telemetry_checksum,
    }


def run(records: int, iterations: int, mode: str, esc: str) -> dict:
    reference = run_scenario(mode, esc)
    scenario_steps = reference["scenario_steps"]
    repeats = max(1, math.ceil(records / scenario_steps))

    wall_samples = []
    cpu_samples = []
    final = reference
    processed_steps = repeats * scenario_steps

    for _ in range(iterations):
        t0 = time.perf_counter()
        c0 = time.process_time()
        checksum = 0
        for _repeat in range(repeats):
            final = run_scenario(mode, esc)
            checksum ^= int(final["telemetry_checksum"])
        cpu_samples.append(time.process_time() - c0)
        wall_samples.append(time.perf_counter() - t0)

    median_wall = statistics.median(wall_samples)
    median_cpu = statistics.median(cpu_samples)
    throughput = processed_steps / median_wall if median_wall else math.inf
    usage = resource.getrusage(resource.RUSAGE_SELF)

    return {
        "architecture": platform.machine(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "mode": mode,
        "esc": esc,
        "records": records,
        "processed_simulation_steps": processed_steps,
        "iterations": iterations,
        "median_wall_seconds": round(median_wall, 6),
        "median_cpu_seconds": round(median_cpu, 6),
        "throughput_records_per_sec": round(throughput, 2),
        "max_rss_kb": int(usage.ru_maxrss),
        "result": final,
        "hostname": platform.node(),
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--records", type=int, default=100_000, help="target total simulation steps")
    p.add_argument("--iterations", type=int, default=3)
    p.add_argument("--mode", choices=("baseline", "optimized"), default="baseline")
    p.add_argument("--esc", choices=("on", "off"), default="on")
    p.add_argument("--output", default="result.json")
    args = p.parse_args()
    if args.records < 1 or args.records > 5_000_000:
        raise SystemExit("--records must be between 1 and 5,000,000")
    if args.iterations < 1 or args.iterations > 20:
        raise SystemExit("--iterations must be between 1 and 20")
    data = run(args.records, args.iterations, args.mode, args.esc)
    Path(args.output).write_text(json.dumps(data, indent=2) + "\n")
    print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
