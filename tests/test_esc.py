#!/usr/bin/env python3
import importlib.util
from pathlib import Path

module_path = Path(__file__).resolve().parents[1] / "benchmark" / "benchmark.py"
spec = importlib.util.spec_from_file_location("esc_benchmark", module_path)
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)

esc_on = bench.run_scenario("optimized", "on")
esc_off = bench.run_scenario("optimized", "off")

assert esc_on["stability_1s_pass"], esc_on
assert esc_on["stability_1_75s_pass"], esc_on
assert esc_on["responsiveness_pass"], esc_on
assert esc_on["simulated_fmvss126_pass"], esc_on
assert not esc_off["simulated_fmvss126_pass"], esc_off

# Both compute modes must preserve the same vehicle-level result.
assert bench.run_scenario("baseline", "on") == esc_on

print("ESC ON:", esc_on)
print("ESC OFF:", esc_off)
