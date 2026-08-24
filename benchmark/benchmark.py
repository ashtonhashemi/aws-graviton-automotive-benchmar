#!/usr/bin/env python3
"""Synthetic automotive CAN/DTC processing benchmark for x86_64 vs AWS Graviton."""
from __future__ import annotations

import argparse
import json
import math
import platform
import random
import resource
import statistics
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Frame:
    timestamp_us: int
    can_id: int
    data: bytes


def build_dataset(records: int, seed: int = 42) -> list[Frame]:
    rng = random.Random(seed)
    frames: list[Frame] = []
    ids = (0x180, 0x181, 0x220, 0x2A0, 0x300, 0x3D0)
    for i in range(records):
        can_id = ids[i % len(ids)]
        speed = rng.randrange(0, 2200)       # 0.1 km/h
        temp = rng.randrange(200, 1500)      # 20.0 to 149.9 C
        voltage = rng.randrange(2800, 4300)  # mV
        flags = 1 if (i % 997 == 0) else 0
        payload = bytes((
            speed & 0xFF, (speed >> 8) & 0xFF,
            temp & 0xFF, (temp >> 8) & 0xFF,
            voltage & 0xFF, (voltage >> 8) & 0xFF,
            flags,
            (can_id ^ i) & 0xFF,
        ))
        frames.append(Frame(i * 10_000, can_id, payload))
    return frames


def process_baseline(frames: list[Frame]) -> dict:
    speeds = []
    temps = []
    faults = 0
    checksum = 0
    for frame in frames:
        d = frame.data
        signals = {
            "speed_kph": (d[1] << 8 | d[0]) / 10.0,
            "temp_c": (d[3] << 8 | d[2]) / 10.0,
            "voltage_mv": d[5] << 8 | d[4],
            "fault_flag": d[6],
        }
        if (signals["fault_flag"] or signals["voltage_mv"] < 3000
                or signals["voltage_mv"] > 4200 or signals["temp_c"] > 130.0):
            faults += 1
        speeds.append(signals["speed_kph"])
        temps.append(signals["temp_c"])
        checksum = (checksum + frame.can_id + sum(d)) & 0xFFFFFFFF
    return {
        "faults": faults,
        "mean_speed_kph": statistics.fmean(speeds),
        "max_temp_c": max(temps),
        "checksum": checksum,
    }


def process_optimized(frames: list[Frame]) -> dict:
    total_speed = 0
    max_temp_raw = -10**9
    faults = 0
    checksum = 0
    n = len(frames)
    for frame in frames:
        d = frame.data
        speed_raw = d[0] | (d[1] << 8)
        temp_raw = d[2] | (d[3] << 8)
        voltage = d[4] | (d[5] << 8)
        total_speed += speed_raw
        if temp_raw > max_temp_raw:
            max_temp_raw = temp_raw
        faults += int(bool(d[6] or voltage < 3000 or voltage > 4200 or temp_raw > 1300))
        checksum = (checksum + frame.can_id + d[0] + d[1] + d[2] + d[3] + d[4] + d[5] + d[6] + d[7]) & 0xFFFFFFFF
    return {
        "faults": faults,
        "mean_speed_kph": (total_speed / n) / 10.0 if n else 0.0,
        "max_temp_c": max_temp_raw / 10.0 if n else 0.0,
        "checksum": checksum,
    }


def run(records: int, iterations: int, mode: str) -> dict:
    frames = build_dataset(records)
    fn = process_optimized if mode == "optimized" else process_baseline
    wall_samples = []
    cpu_samples = []
    result = None
    for _ in range(iterations):
        t0 = time.perf_counter()
        c0 = time.process_time()
        result = fn(frames)
        cpu_samples.append(time.process_time() - c0)
        wall_samples.append(time.perf_counter() - t0)

    median_wall = statistics.median(wall_samples)
    median_cpu = statistics.median(cpu_samples)
    throughput = records / median_wall if median_wall else math.inf
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return {
        "architecture": platform.machine(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "mode": mode,
        "records": records,
        "iterations": iterations,
        "median_wall_seconds": round(median_wall, 6),
        "median_cpu_seconds": round(median_cpu, 6),
        "throughput_records_per_sec": round(throughput, 2),
        "max_rss_kb": int(usage.ru_maxrss),
        "result": result,
        "hostname": platform.node(),
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--records", type=int, default=500_000)
    p.add_argument("--iterations", type=int, default=5)
    p.add_argument("--mode", choices=("baseline", "optimized"), default="baseline")
    p.add_argument("--output", default="result.json")
    args = p.parse_args()
    if args.records < 1 or args.records > 5_000_000:
        raise SystemExit("--records must be between 1 and 5,000,000")
    if args.iterations < 1 or args.iterations > 20:
        raise SystemExit("--iterations must be between 1 and 20")
    data = run(args.records, args.iterations, args.mode)
    Path(args.output).write_text(json.dumps(data, indent=2) + "\n")
    print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
