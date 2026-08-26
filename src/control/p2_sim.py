from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass


@dataclass(frozen=True)
class LogNormalMs:
    median_ms: float
    sigma: float
    minimum_ms: float = 0.0
    maximum_ms: float = math.inf

    def sample(self, rng: random.Random) -> float:
        value = rng.lognormvariate(math.log(self.median_ms), self.sigma)
        return min(self.maximum_ms, max(self.minimum_ms, value))


@dataclass(frozen=True)
class NormalMs:
    mean_ms: float
    sigma_ms: float
    minimum_ms: float
    maximum_ms: float

    def sample(self, rng: random.Random) -> float:
        return min(self.maximum_ms, max(self.minimum_ms, rng.gauss(self.mean_ms, self.sigma_ms)))


ARCHITECTURES = {
    "distributed_canfd": {
        "label": "Distributed gateway + CAN-FD",
        "components": {
            "Tester / DoIP RTT": LogNormalMs(0.25, 0.35, 0.05, 1.5),
            "Diagnostic gateway RTT": LogNormalMs(0.35, 0.40, 0.05, 2.0),
            "CAN-FD last-mile RTT": LogNormalMs(1.20, 0.50, 0.15, 8.0),
        },
    },
    "zonal_hpc_proxy": {
        "label": "Zonal HPC diagnostic proxy",
        "components": {
            "Tester / DoIP RTT": LogNormalMs(0.25, 0.35, 0.05, 1.5),
            "Ethernet switching RTT": LogNormalMs(0.24, 0.35, 0.03, 2.4),
            "Zone forwarding RTT": LogNormalMs(0.15, 0.40, 0.02, 1.2),
            "HPC request proxy": LogNormalMs(1.50, 0.70, 0.10, 15.0),
            "HPC response proxy": LogNormalMs(1.50, 0.70, 0.10, 15.0),
        },
    },
}

PROFILES = {
    "nominal": NormalMs(20.0, 7.0, 3.0, 45.0),
    "near_limit": NormalMs(38.0, 5.0, 20.0, 49.0),
}


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(q * len(ordered)) - 1))
    return ordered[index]


def histogram(values: list[float], budget_ms: float) -> list[dict]:
    upper = max(100.0, budget_ms * 2.0, math.ceil(max(values) / 5.0) * 5.0)
    bins = 40
    width = upper / bins
    counts = [0] * bins
    for value in values:
        idx = min(bins - 1, int(value / width))
        counts[idx] += 1
    return [
        {"from_ms": round(i * width, 2), "to_ms": round((i + 1) * width, 2), "count": count}
        for i, count in enumerate(counts)
    ]


def server_model(profile: str, custom: dict | None) -> NormalMs:
    if profile != "custom":
        return PROFILES[profile]
    custom = custom or {}
    mean = float(custom.get("mean_ms", 38.0))
    sigma = float(custom.get("sigma_ms", 5.0))
    minimum = float(custom.get("minimum_ms", 1.0))
    maximum = float(custom.get("maximum_ms", 49.0))
    if not (0 < mean <= 1000 and 0 <= sigma <= 500 and 0 <= minimum <= maximum <= 2000):
        raise ValueError("invalid custom ECU timing profile")
    return NormalMs(mean, sigma, minimum, maximum)


def simulate_one(name: str, model: NormalMs, samples: int, seed: int, budget_ms: float) -> dict:
    rng = random.Random(seed)
    totals: list[float] = []
    server_values: list[float] = []
    architecture_values: list[float] = []
    component_sums: dict[str, float] = {}

    for _ in range(samples):
        server_ms = model.sample(rng)
        components = {label: distribution.sample(rng) for label, distribution in ARCHITECTURES[name]["components"].items()}
        architecture_ms = sum(components.values())
        total = server_ms + architecture_ms
        server_values.append(server_ms)
        architecture_values.append(architecture_ms)
        totals.append(total)
        for label, value in components.items():
            component_sums[label] = component_sums.get(label, 0.0) + value

    misses = sum(value > budget_ms for value in totals)
    return {
        "architecture": name,
        "label": ARCHITECTURES[name]["label"],
        "samples": samples,
        "p2tester_budget_ms": budget_ms,
        "server_processing_ms": {
            "mean": round(statistics.fmean(server_values), 3),
            "p95": round(percentile(server_values, 0.95), 3),
            "p99": round(percentile(server_values, 0.99), 3),
        },
        "architecture_delay_ms": {
            "mean": round(statistics.fmean(architecture_values), 3),
            "p95": round(percentile(architecture_values, 0.95), 3),
            "p99": round(percentile(architecture_values, 0.99), 3),
            "mean_components": {label: round(value / samples, 3) for label, value in component_sums.items()},
        },
        "p2tester_elapsed_ms": {
            "mean": round(statistics.fmean(totals), 3),
            "p50": round(percentile(totals, 0.50), 3),
            "p95": round(percentile(totals, 0.95), 3),
            "p99": round(percentile(totals, 0.99), 3),
            "max": round(max(totals), 3),
        },
        "budget_miss_count": misses,
        "budget_miss_pct": round(100.0 * misses / samples, 3),
        "meets_99_percent": percentile(totals, 0.99) <= budget_ms,
        "histogram": histogram(totals, budget_ms),
    }


def run_study(body: dict) -> dict:
    samples = int(body.get("samples", 20000))
    budget_ms = float(body.get("budget_ms", 50.0))
    profile = body.get("profile", "nominal")
    architecture = body.get("architecture", "all")
    seed = int(body.get("seed", 42))

    if not 100 <= samples <= 100000:
        raise ValueError("samples must be between 100 and 100000")
    if not 1.0 <= budget_ms <= 5000.0:
        raise ValueError("budget_ms must be between 1 and 5000")
    if profile not in ("nominal", "near_limit", "custom"):
        raise ValueError("profile must be nominal, near_limit, or custom")
    if architecture != "all" and architecture not in ARCHITECTURES:
        raise ValueError("invalid architecture")

    model = server_model(profile, body.get("custom_server"))
    names = list(ARCHITECTURES) if architecture == "all" else [architecture]
    results = [simulate_one(name, model, samples, seed + index, budget_ms) for index, name in enumerate(names)]
    return {
        "study": "OBDonUDS P2Tester architecture timing trade study",
        "mode": "engineering Monte Carlo model",
        "note": "Delay distributions are explicit engineering assumptions, not normative SAE/ISO timing values. Replace them with measured vehicle data when available.",
        "profile": profile,
        "results": results,
    }
