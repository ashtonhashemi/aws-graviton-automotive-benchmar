#!/usr/bin/env python3
"""Monte Carlo P2Tester timing study for distributed vs zonal OBDonUDS architectures.

The model separates target-ECU processing from architecture-dependent round-trip
transport delay. It is intended for engineering trade studies, not compliance
certification. Default distributions are explicit assumptions and should be
replaced with measured vehicle data when available.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import statistics
from dataclasses import dataclass
from pathlib import Path

P2_TESTER_BUDGET_MS = 50.0


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
        "label": "Distributed gateway + CAN-FD target ECU",
        "components": {
            "tester_doip_each_way": LogNormalMs(0.25, 0.35, 0.05, 1.5),
            "gateway_each_way": LogNormalMs(0.35, 0.40, 0.05, 2.0),
            "canfd_last_mile_each_way": LogNormalMs(1.20, 0.50, 0.15, 8.0),
        },
        "round_trip_multiplier": 2,
    },
    "zonal_transparent": {
        "label": "Zonal transparent Ethernet routing",
        "components": {
            "tester_doip_each_way": LogNormalMs(0.25, 0.35, 0.05, 1.5),
            "ethernet_switch_hop_each_way": LogNormalMs(0.08, 0.40, 0.01, 0.8),
            "zone_forwarding_each_way": LogNormalMs(0.15, 0.40, 0.02, 1.2),
        },
        "switch_hops_each_way": 3,
        "round_trip_multiplier": 2,
    },
    "zonal_hpc_proxy": {
        "label": "Zonal HPC diagnostic proxy",
        "components": {
            "tester_doip_each_way": LogNormalMs(0.25, 0.35, 0.05, 1.5),
            "ethernet_switch_hop_each_way": LogNormalMs(0.08, 0.40, 0.01, 0.8),
            "zone_forwarding_each_way": LogNormalMs(0.15, 0.40, 0.02, 1.2),
            "hpc_proxy_request": LogNormalMs(1.50, 0.70, 0.10, 15.0),
            "hpc_proxy_response": LogNormalMs(1.50, 0.70, 0.10, 15.0),
        },
        "switch_hops_each_way": 3,
        "round_trip_multiplier": 2,
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


def transport_delay_ms(name: str, rng: random.Random) -> tuple[float, dict[str, float]]:
    cfg = ARCHITECTURES[name]
    c = cfg["components"]
    parts: dict[str, float] = {}

    if name == "distributed_canfd":
        parts["tester_doip_round_trip"] = 2 * c["tester_doip_each_way"].sample(rng)
        parts["gateway_round_trip"] = 2 * c["gateway_each_way"].sample(rng)
        parts["canfd_last_mile_round_trip"] = 2 * c["canfd_last_mile_each_way"].sample(rng)
    else:
        parts["tester_doip_round_trip"] = 2 * c["tester_doip_each_way"].sample(rng)
        hop_sum = sum(c["ethernet_switch_hop_each_way"].sample(rng) for _ in range(cfg["switch_hops_each_way"]))
        parts["ethernet_switching_round_trip"] = 2 * hop_sum
        parts["zone_forwarding_round_trip"] = 2 * c["zone_forwarding_each_way"].sample(rng)
        if name == "zonal_hpc_proxy":
            parts["hpc_proxy_request"] = c["hpc_proxy_request"].sample(rng)
            parts["hpc_proxy_response"] = c["hpc_proxy_response"].sample(rng)

    return sum(parts.values()), parts


def simulate(architecture: str, profile: str, samples: int, seed: int, budget_ms: float) -> dict:
    rng = random.Random(seed)
    server_model = PROFILES[profile]
    totals: list[float] = []
    transports: list[float] = []
    servers: list[float] = []
    component_sums: dict[str, float] = {}

    for _ in range(samples):
        server_ms = server_model.sample(rng)
        transport_ms, components = transport_delay_ms(architecture, rng)
        total = server_ms + transport_ms
        servers.append(server_ms)
        transports.append(transport_ms)
        totals.append(total)
        for key, value in components.items():
            component_sums[key] = component_sums.get(key, 0.0) + value

    misses = sum(value > budget_ms for value in totals)
    return {
        "architecture": architecture,
        "label": ARCHITECTURES[architecture]["label"],
        "profile": profile,
        "samples": samples,
        "p2tester_budget_ms": budget_ms,
        "server_processing_ms": {
            "mean": round(statistics.fmean(servers), 3),
            "p95": round(percentile(servers, 0.95), 3),
            "p99": round(percentile(servers, 0.99), 3),
        },
        "architecture_delay_ms": {
            "mean": round(statistics.fmean(transports), 3),
            "p95": round(percentile(transports, 0.95), 3),
            "p99": round(percentile(transports, 0.99), 3),
            "mean_components": {key: round(value / samples, 3) for key, value in component_sums.items()},
        },
        "p2tester_elapsed_ms": {
            "mean": round(statistics.fmean(totals), 3),
            "p95": round(percentile(totals, 0.95), 3),
            "p99": round(percentile(totals, 0.99), 3),
            "max": round(max(totals), 3),
        },
        "budget_miss_count": misses,
        "budget_miss_pct": round(100.0 * misses / samples, 3),
        "meets_99_percent": percentile(totals, 0.99) <= budget_ms,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=100_000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--budget-ms", type=float, default=P2_TESTER_BUDGET_MS)
    parser.add_argument("--profile", choices=tuple(PROFILES), default="nominal")
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    if args.samples < 100:
        raise SystemExit("--samples must be at least 100")

    results = [simulate(name, args.profile, args.samples, args.seed + i, args.budget_ms)
               for i, name in enumerate(ARCHITECTURES)]
    payload = {
        "study": "SAE J1979-2 / OBDonUDS P2Tester architecture timing trade study",
        "note": "Engineering simulation. Delay distributions are explicit assumptions, not normative SAE/ISO values.",
        "results": results,
    }
    text = json.dumps(payload, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(text)
    print(text, end="")


if __name__ == "__main__":
    main()
