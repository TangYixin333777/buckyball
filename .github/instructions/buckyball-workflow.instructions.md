---
name: buckyball-workflow
description: Workflow constraints for Ball authoring, registration, and validation.
applyTo: "**/*.{md,scala,json,py,c,cpp}"
---

# Buckyball Workflow Rules

- Follow `.buckyball-rules/00-orchestration.md` for stage transitions.
- Keep Ball authoring changes under `arch/src/main/scala/framework/balldomain/prototype/`.
- Keep registration changes limited to mapping/generator/decode planes.
- Emit contract JSON blocks exactly as required by skills.
- Use runtime CTest verification before reporting completion; static validation is optional dry-run.

## Runtime evidence policy (mandatory)

- Use `stdout.log` in the latest simulation `log_dir` as primary strict PASS/FAIL evidence.
- Use `bdb.ndjson` (fallback: `bdb.log`) as supplemental trace evidence and activity summary.
- Runtime results must always be labeled with one classification:
	- `strict_pass` (explicit PASS evidence in `stdout.log` with successful runtime chain)
	- `heuristic_pass` (no explicit PASS but no failure evidence)
	- `fail` (any failure evidence or non-zero runtime step)
- `fail` and `heuristic_pass` must enter debug-only workflow; do not run Yosys/OpenSTA in this branch.
- Yosys/OpenSTA optimization is allowed only after at least one `strict_pass` has been achieved in current iteration.
- During optimize mode, if worst-path slack from timing report is negative, immediately route to debug timing-fix loop and continue until slack > 0.

## Terminal execution safety (mandatory)

- Apply single-flight command policy for any long-running build/run command.
- After starting a runtime/build command, do not issue another command in the same terminal/session until explicit completion (exit code or MCP quiescence completion) is returned.
- Do not run ad-hoc `tail/grep/cat` log commands while build/run is active in that same terminal.
- Prefer MCP post-run log tools (`find_latest_bdb_log`, `summarize_bdb_log`) after command completion.
- If output appears quiet, treat as still-running and wait for quiescence result instead of sending probe commands.
- If an interruption happened, stop retry loop, restart from last stable stage once, and report the interruption cause.
