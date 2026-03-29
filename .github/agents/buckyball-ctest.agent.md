---
name: buckyball-ctest
description: Prepare/register CTest workloads and ISA hooks only (no runtime execution).
user-invocable: false
tools: [vscode, execute, read, edit, search, 'buckyball-mcp/*']
---

# Buckyball CTest

Prepare toy workload tests according to:

- `.github/skills/buckyball-ctest-author-from-rules/SKILL.md`
- `bb-tests/workloads/src/CTest/toy/CMakeLists.txt`

## Scope

- Add/update `bb-tests/workloads/src/CTest/toy/*.c`
- Add registration entries in `bb-tests/workloads/src/CTest/toy/CMakeLists.txt`
- Add/update ISA helper files in `bb-tests/workloads/lib/bbhw/isa/*.c`
- Add ISA include registration in `bb-tests/workloads/lib/bbhw/isa/isa.h`
- Produce runtime handoff metadata (`test_target`, `binary_name`, `config`) for `buckyball-test-runtime`
	- Canonical runtime mapping: `binary_name = <test_target>_singlecore-baremetal`

## Responsibility boundary (strict)

- `buckyball-ctest` must NOT run simulation commands.
- `buckyball-ctest` must NOT run `run_bbdev_test_compile`, `run_bbdev_workload_build`, `run_bbdev_verilog`, or `run_bbdev_verilator`.
- Actual runtime execution and log inspection are owned by `buckyball-test-runtime` only.

Return CTest/ISA artifact changes, runtime handoff metadata, and explicit registration-check evidence in chat output:
- CTest target exists in group CMake registration
- Target is included in `buckyball-CTest-build` dependency
- ISA include exists in `bb-tests/workloads/lib/bbhw/isa/isa.h`
- Runtime metadata (`test_target`, `binary_name`, `config`) is self-consistent
- Semantic validity evidence (`self_fulfilling_oracle=false`, independent oracle source, and at least one non-trivial activation case or blocked reason)
