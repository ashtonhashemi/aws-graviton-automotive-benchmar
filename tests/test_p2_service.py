#!/usr/bin/env python3
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "control"))

from p2_sim import run_study


def main():
    data = run_study({
        "architecture": "all",
        "profile": "near_limit",
        "budget_ms": 50,
        "samples": 5000,
        "seed": 42,
    })
    results = {item["architecture"]: item for item in data["results"]}
    assert set(results) == {"distributed_canfd", "zonal_hpc_proxy"}
    for result in results.values():
        assert result["p2tester_elapsed_ms"]["p99"] > 0
        assert len(result["histogram"]) == 40
        assert 0 <= result["budget_miss_pct"] <= 100
    assert results["distributed_canfd"]["p2tester_elapsed_ms"]["p99"] != results["zonal_hpc_proxy"]["p2tester_elapsed_ms"]["p99"]
    print("P2Tester two-architecture dashboard service regression passed")


if __name__ == "__main__":
    main()
