# Tuning plan

The project deliberately separates **architecture comparison** from **software tuning**.

## Experiment matrix

Run the same record count and iteration count for each case:

| Test | x86_64 | Graviton ARM64 |
|---|---|---|
| Baseline Python loop | Yes | Yes |
| Optimized Python loop | Yes | Yes |

Capture median wall time, CPU time, throughput, memory high-water mark, instance type, Python version, and a checksum to prove both paths processed equivalent data.

## First tuning step already implemented

`baseline` creates temporary speed and temperature lists and uses higher-level statistics after the loop. `optimized` keeps integer accumulators, removes those temporary lists, avoids repeated conversions, and reduces per-frame work.

## Good next iterations

1. Add a C/Rust implementation and compile it natively on each architecture.
2. Build ARM64 and x86_64 container images and compare containerized execution.
3. Add multi-process scaling at 1, 2, and 4 workers.
4. Compare compiler flags such as `-O2`, `-O3`, and architecture-specific tuning.
5. Add cost-per-million-records after capturing the current EC2 on-demand price for the selected region.

Do not change workload size, data seed, or pass/fail logic between architectures in the same comparison.
