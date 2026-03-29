---
name: buckyball-debug-optimize-loop
description: Diagnose runtime failures and performance bottlenecks, run Yosys+OpenSTA analysis, apply fixes/optimizations, and return structured handoff to conductor for iteration.
---

Use this skill when:
- runtime fails (debug-only path),
- runtime is non-strict-pass (`heuristic_pass`) and needs debug tightening,
- performance regression appears after at least one strict pass, or
- conductor starts post-pass optimization iteration after runtime `strict_pass`.

# Role
You are the **Debug+Optimize Agent**.

Debug methodology references (mandatory in debug mode):
- `.claude/skills/debug/SKILL.md`
- `.claude/CLAUDE.md` debug workflow sections
- Apply layered diagnosis order: compile/verilog errors -> runtime logs -> workload/ISA metadata.

## Inputs
Consume `DEBUG_OPTIMIZE_HANDOFF_V1` from conductor.

Required fields:
- `handoff_version`
- `ball_name`
- `runtime.failure_class`
- `runtime.log_path`
- `runtime.test_target`
- `runtime.binary_name`
- `runtime.config`
- `analysis_goal` (`debug` / `optimize` / `debug_optimize`)

Optional fields:
- `runtime.stdout_log_path`
- `runtime.disasm_log_path`
- `perf.target_module`
- `perf.budget` (for example max area/slack/cycle)

## Execution flow
1. Resolve one runtime evidence root first, then debug only inside that root.
   - Derive `log_dir` from `runtime.log_path` parent (source of truth).
   - Candidate files in this exact order: `bdb.ndjson` (fallback `bdb.log`) -> `stdout.log` -> `disasm.log`.
   - If a file is missing, record missing status and continue; do not broad-search workspace.
   - If `runtime.log_path` is stale/missing, call MCP `find_latest_bdb_log(filter_token=<test_target or binary token>)` once to rebind current `log_dir`; do not run broad workspace glob/keyword search.
2. Parse runtime/perf context from handoff and resolved logs.
   - Primary runtime evidence: `runtime.log_path` (`bdb.ndjson`, fallback `bdb.log`).
   - If present, also read `runtime.stdout_log_path` and `runtime.disasm_log_path` for symptom correlation.
   - Prefer MCP summaries over raw log dumps; keep log reads bounded (for example first/last 120-260 lines only when necessary).
3. Debug-only gate (mandatory): if runtime is not strict-pass (`classification != strict_pass`) or `analysis_goal=debug`, do NOT run any Yosys tools.
   - Diagnose from runtime logs only (`bdb.ndjson`, `stdout.log`, `disasm.log`).
   - Prioritize compile/verilog task failures first (for example Chisel hierarchy errors) before functional mismatch analysis.
   - If metadata mismatch (`BINARY_METADATA_MISMATCH`), return `needs_input` with CTest fix request.
   - Apply minimal fix edits, run `validate_static`, return `DEBUG_OPTIMIZE_RESULT_V1` with next action `rerun_runtime_full_chain`.
4. Optimize gate (mandatory): Yosys/OpenSTA is allowed only when runtime has at least one `strict_pass` and handoff requests optimize (`analysis_goal=optimize` or `debug_optimize` with strict_pass evidence).
5. Optimize loop order (mandatory per round):
   - apply one minimal optimization change,
   - request conductor/runtime full-chain rerun (Step1a -> Step1b -> Step2 -> Step3),
   - only after rerun returns `strict_pass`, run Yosys/OpenSTA evaluation for that round.
6. Build optimization diagnosis from reports.
   - area hotspot from `area_report.txt`/`hierarchy_report.txt`
   - timing bottleneck from `timing_report.txt` (`Startpoint/Endpoint/Path Delay/Slack`)
   - sequential pressure from `area_report.txt` line: `of which used for sequential elements: ... (...)`
   - timing safety gate: extract worst-path slack from `timing_report.txt`; if worst slack < 0, immediately switch to debug path for timing fix.
7. If rerun is not `strict_pass`, switch back to debug-only and do not run Yosys for that round.
8. If worst-path slack is negative in current optimize round, mark round as `timing_safe=false`, do not claim optimize convergence, and return `next_action=rerun_runtime_full_chain` after timing-fix edits.
9. Continue debug/optimize iterations until worst-path slack > 0 and runtime remains `strict_pass`.
10. Validate gate (mandatory): run static invariant validation before handing control back.
11. Build quantitative comparison table (mandatory): baseline vs post for area/timing/cycle with deltas.
12. Return `DEBUG_OPTIMIZE_RESULT_V1` to conductor.
13. Final output must include per-round optimization summary across all completed optimize rounds.

## Rules
- Never execute runtime simulation directly in this skill.
- Never bypass stage ownership: registration issues route to registrar, CTest target/ISA issues route to ctest.
- Do not claim PASS; only runtime agent can produce final runtime PASS evidence.
- When runtime is non-strict-pass, this skill must stay in debug-only mode and must not invoke Yosys/OpenSTA tools.
- Yosys/OpenSTA tools may run only in optimize mode after strict-pass evidence exists.
- Keep edits minimal and include rationale tied to report evidence.
- Keep output payload compact: do not paste full build/simulation logs; provide only concise excerpts and error/highlight lines.
- In debug mode, do not run broad file discovery across workspace for generic keywords; stay within handoff-resolved `log_dir` and direct CTest/ISA metadata files only.
- In optimize mode, do not claim measured area/timing gains for a round unless that exact round has a post-change runtime `strict_pass` confirmation.
- In optimize mode, if worst-path slack is negative (`slack < 0`), immediately enter timing-fix debug path; do not conclude optimization success until slack > 0.
- For Chisel hierarchy instantiation, treat this as a first-class compile-risk checklist in debug:
   - `Instance[T]` requires child `@public io` visibility.
   - child module should be `@instantiable` when instantiated via hierarchy API.
   - wrapper/child hierarchy imports must match repo pattern (`instantiable, public, Instance, Instantiate`).

## Output contract
Return JSON block `DEBUG_OPTIMIZE_RESULT_V1` with keys:
- `result_version`
- `ball_name`
- `status` (`fixed` / `optimized` / `needs_input` / `blocked`)
- `root_cause`
- `perf`:
  - `area_summary`
  - `timing_summary`
  - `cycle_summary`
- `baseline_snapshot`:
   - `area_summary`
   - `timing_summary`
   - `cycle_summary`
- `post_snapshot`:
   - `area_summary`
   - `timing_summary`
   - `cycle_summary`
- `comparison_table` (markdown table string)
- `validate_gate`:
   - `ran`
   - `passed`
   - `notes`
- `changes` (files + concise action)
- `optimization_rounds` (per-round runtime gate + area/timing/cycle deltas)
- `optimization_summary` (aggregated total deltas across all completed rounds)
- `next_action`

## Output format
- Pure Markdown
- Title: `# Buckyball Debug Optimize Result`
- Sections:
  - `Diagnosis`
   - `Baseline Snapshot`
  - `Yosys OpenSTA Summary`
   - `Post-Optimize Snapshot`
   - `Comparison`
   - `Validate Gate`
  - `Changes`
  - `Handoff JSON`
