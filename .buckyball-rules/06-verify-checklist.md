# Buckyball Verification Checklist

scope: validation
source_of_truth:
- bbdev/api/steps/workload/01_buidl_api_step.py
- bbdev/api/steps/workload/01_build_event_step.py
- bbdev/api/steps/verilator/README.md
- scripts/mcp/buckyball_mcp_server.py

## default_gate_runtime_ctest

- Default chain completion requires runtime CTest verification.
- Static checks are optional and can run as preflight dry-run.

## runtime_checks_default

- Prepare/register test workload under `bb-tests/workloads/src/CTest/<group>/`.
- Run `bbdev workload --build` successfully.
- Run `bbdev verilator --run ...` successfully.
- Resolve latest `arch/log/*/bdb.ndjson` (fallback: `bdb.log`) and extract pass/fail summary.

## runtime_stdout_evidence_standard

- Runtime strict evidence is based on explicit PASS/FAIL output in simulation `stdout.log` under latest `arch/log/<timestamp>-*/` directory.
- `bdb.ndjson` (fallback: `bdb.log`) is supplemental evidence for command activity and trace diagnosis, not the only strict PASS source.
- If `stdout.log` is missing, classification must degrade to `heuristic_pass` (when no failure evidence) or `fail` (when failure evidence exists).

## static_checks

- Rules files exist and readable.
- Author output includes valid BALL_HANDOFF_V1 JSON.
- Registrar output includes valid BALL_REGISTRATION_RESULT_V1 JSON.
- Invariants:
  - decode.bid == mapping.ballId
  - mapping.ballName == ball_name
  - ballName == wrapper class simple name
  - ballNum == ballIdMappings count
  - no duplicate ballId
  - no duplicate funct7/value symbol
  - all bank channels default to safe values before FSM override (`req.valid=false`, `resp.ready=false`)
  - `resp.ready` asserted only on lanes consumed by current state logic
  - read-data layout contract declared (`scalar-per-address` or `packed-word`) and implementation matches declaration
  - implementation is not address-hardcoded for non-benchmark paths (no unconditional read/write addr=0 for iterative workloads)
  - command iteration fields (`iter` or equivalent) participate in runtime progression when workload is multi-tile
  - any fixed-size limitation is documented under `Robustness Exception` with reason and scope

## optional_ci_aligned_checks

- skipped in current development stage

## optional_mcp_checks

- python3 scripts/mcp/buckyball_mcp_server.py
- Validate with tool call: `validate_static` (dry-run style contract check before apply)
- Execute with MCP runtime tools:
  - `run_bbdev_workload_build`
  - `run_bbdev_verilator`
  - `find_latest_bdb_log`
  - `summarize_bdb_log`

## yosys_report_checks (optimize mode only)

- Read `bbdev/api/steps/yosys/log/hierarchy_report.txt` for hierarchy-level hotspot modules.
- Read `bbdev/api/steps/yosys/log/area_report.txt` for chip area and sequential ratio.
- Read `bbdev/api/steps/yosys/log/timing_report.txt` for `Startpoint`, `Endpoint`, `Path Delay`, and `Slack`.
- Optimization comparison should report baseline/post deltas for area and timing using the above files.

## pass_criteria

- Runtime CTest checks pass with no execution errors.
- `strict_pass`: runtime command chain succeeds and latest `stdout.log` contains explicit PASS evidence for current test.
- `heuristic_pass`: runtime command chain succeeds and no fail evidence is found, but explicit PASS evidence is absent.
- If only heuristic evidence is available, report classification explicitly as `heuristic_pass`.
- If optional static/CI checks are requested, commands return success.

## debug_optimize_role_split (mandatory)

- If runtime has any step error or classification is not `strict_pass` (`fail`/`heuristic_pass`), enter debug-only mode.
- Debug-only mode must use runtime logs (`bdb.ndjson`/`bdb.log`, `stdout.log`, `disasm.log`) and must not invoke Yosys/OpenSTA.
- Yosys/OpenSTA timing/area optimization is allowed only after at least one `strict_pass` exists.

## failure_cases

- Any contract JSON parse failure.
- Any invariant mismatch.
- Missing latest `bdb.ndjson`/`bdb.log` after runtime test execution.
- Missing latest `stdout.log` after runtime test execution (unless explicitly waived by policy).
- Runtime command returns non-zero.
- CI command returns non-zero.
