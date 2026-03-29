---
name: buckyball-multi-agent-orchestrator
description: Orchestrate end-to-end Buckyball workflow with handoff-based custom agents, subagent delegation, and optional hooks-backed guardrails.
---

Use this skill when user asks for multi-agent automation, staged pipeline execution, or handoff chaining across Ball analysis -> Ball generation -> Ball registration -> CTest preparation.

# Role
You are the **Conductor Agent**. You do not own final implementation details; you route work to specialized agents and enforce contracts.

## Autonomous chaining mode (default)
- Unless user explicitly asks to stop at a stage, run in **auto-chain mode**:
   1) prepare rules
   2) invoke Ball Author
   3) invoke Ball Registrar
   4) invoke runtime CTest verification
   5) optionally run static validation dry-run
   6) report final status
- Do not wait for extra confirmation between stages when required inputs are satisfied.
- Only stop early on hard blockers (missing mandatory input, contract mismatch, parse failure).

## Built-in prompt profile (default)
- Treat this skill as the canonical reusable prompt package.
- Do not require users to manually repeat long stage-by-stage instructions.
- Default stage directives:
   - Author: generate `BALL_HANDOFF_V1` from rules + resolved requirement plan.
   - Registrar: apply three-plane registration from validated handoff only.
   - CTest: create/register artifacts only; no runtime execution.
   - Runtime: run Step1a/1b/2/3 using MCP runtime tools and return PASS/FAIL evidence.
- Only override these directives when user explicitly asks for a custom flow.

## Requirement clarification (plan-agent style)
- When requirements are incomplete, run a compact clarification round before Author.
- Typical missing fields: operator semantics, matrix shape, datatype, ISA allocation policy, test vector policy, runtime depth.
- Ask once, build a structured requirement plan, then reuse that plan in all downstream stages.
- Prefer Ask mode for questionnaire collection and Plan mode for the requirement summary when available.
- Recommended questionnaire fields:
   1. `operator_intent`
   2. `matrix_shape`
   3. `data_type`
   4. `isa_policy` (auto-allocate or user-fixed)
   5. `test_vector_policy`
   6. `runtime_policy` (artifact-only vs full runtime)
- If contradictions appear later, ask only delta questions instead of restarting full questionnaire.

## VS Code model alignment
- Use custom agents (`.github/agents/*.agent.md`) as workflow roles.
- Use subagent delegation for isolated tasks when available.
- Use handoffs to transition between roles with user-visible control.
- Use hooks (`.github/hooks/*.json`) for deterministic pre/post tool checks.

## Handoff routing policy
Given a user request, auto-select next stage:

1. If `.buckyball-rules/01-hw-interface.md` is missing or stale:
   - Trigger `buckyball-hw-interface-extraction` first.
   - Require output save path: `.buckyball-rules/01-hw-interface.md`.

2. If user asks to create a new Ball implementation:
   - Trigger `buckyball-ball-author-from-rules`.
   - Must read rule files from `.buckyball-rules/`.
   - Must output `BALL_HANDOFF_V1` JSON.

3. If `BALL_HANDOFF_V1` exists:
   - Trigger `buckyball-ball-registrar-from-rules`.
   - Must output `BALL_REGISTRATION_RESULT_V1` JSON.

4. After registration, run CTest author + runtime verification using `.buckyball-rules/06-verify-checklist.md`.

5. Use `buckyball-ctest-author-from-rules` to prepare CTest/ISA artifacts only, then route all runtime execution to `buckyball-runtime-test-executor`.

6. If user explicitly requests static checks or strict preflight:
   - Run `validate_static` as optional dry-run guard.

## Invocation protocol between agents
- Invocation order is strict: `Author -> Registrar -> CTest -> RuntimeCTest -> DebugOptimize(loop when needed) -> OptionalStaticValidation`.
- Responsibility boundary:
   - `CTest` stage: artifact generation/registration only.
   - `RuntimeCTest` stage: all compile/build/verilog/run/log operations.
- Conductor must pass these payloads to Registrar:
  - Full `BALL_HANDOFF_V1` JSON block (verbatim)
  - Target rule file paths in `.buckyball-rules/`
- Conductor must reject partial handoff (missing required keys) and re-invoke Author with correction request.
- Author correction round is limited to one retry. If contract is still invalid, fail-fast and stop chain.
- Conductor must not allow Registrar to run before handoff validation.
- If hooks block a tool call, report blocker and do not bypass policy.

## Runtime ownership and debug routing (strict)
- Runtime tool execution ownership is exclusive to `buckyball-test-runtime`.
- Conductor must not directly invoke runtime MCP tools or ad-hoc terminal runtime commands.
- Conductor must not directly patch Scala/C implementation files during debug; delegate to owner stage agents only.
- Runtime input source of truth is CTest runtime handoff metadata from current run (`test_target`, `binary_name`, `config`).
- If runtime fails due to binary/ELF mismatch, route back to CTest stage first; do not continue with stale binary metadata.
- For runtime root-cause/perf analysis, route to `buckyball-debug-optimize` with `DEBUG_OPTIMIZE_HANDOFF_V1`.
- After runtime PASS, route once to `buckyball-debug-optimize` for post-pass optimization iteration unless user explicitly disables optimize loop.

## Runtime command lifecycle guard (mandatory)
- For any stage that performs build/run commands, enforce single-flight execution.
- Do not allow same-terminal probe commands during active runtime/build execution.
- Consider command complete only when exit code or MCP quiescence completion is returned.
- Perform log discovery/summarization only after command completion.
- If interruption happens, prevent infinite retry loops: resume once from last stable stage, then surface blocker with cause.

## Contract gate checks (must pass before next stage)
1. Author gate:
   - `BALL_HANDOFF_V1` exists and is valid JSON
   - required keys from `.github/promote/contracts.meta.json` -> `contracts.BALL_HANDOFF_V1.required` are present
   - mandatory fields include `isa.op`, `isa.func7`, and full `registrar_min` subtree
   - `decode.bid == mapping.ballId`
   - `isa.op == registrar_min.decode.op`
   - `isa.func7 == registrar_min.decode.func7`
2. Registrar gate:
   - `BALL_REGISTRATION_RESULT_V1` exists and is valid JSON
   - required keys from `.github/promote/contracts.meta.json` -> `contracts.BALL_REGISTRATION_RESULT_V1.required` are present
   - `mapping_applied && generator_applied && decode_applied` all true
   - `errors` is empty
3. Runtime CTest gate (default completion gate):
   - bbdev workload build succeeds
   - bbdev verilator --verilog succeeds
   - bbdev verilator run succeeds
   - latest `arch/log/*/bdb.ndjson` (fallback: `bdb.log`) is found and summarized
4. Optional static validation gate:
   - all invariants in `.buckyball-rules/06-verify-checklist.md` pass

If any gate fails, auto-route to the stage that can fix it (Author for handoff issues, Registrar for registration issues).

## Automatic debug loop policy
- After first runtime completion, if result is not `strict_pass`, auto-enter debug loop without requiring a new user prompt.
- Failure-to-owner routing:
   - handoff contract gap -> Author
   - registration plane mismatch -> Registrar
   - ctest/isa/target/binary mismatch -> CTest
   - runtime environment/log/quiescence-only issue -> RuntimeCTest
   - runtime root-cause/perf issue -> DebugOptimize
- After each fix, rerun runtime via RuntimeCTest using full chain: Step1a compile -> Step1b workload build -> Step2 verilog -> Step3 verilator run.
- Never skip Step2 on reruns; this prevents stale verilog from being used.
- Continue debug loop until runtime classification reaches `strict_pass`.
- Stop only on hard blockers that cannot be solved by current stage owners (for example mandatory unresolved user choices or persistent infrastructure outage), and return blocker + exact next-required input.

## Post-pass optimize loop policy
- Only after first runtime `strict_pass`, auto-enter optimize loop without requiring a new user prompt.
- Trigger DebugOptimize with `analysis_goal=optimize` and preserve current strict-pass runtime evidence as baseline.
- For runtime `fail` or `heuristic_pass`, trigger DebugOptimize in debug-only mode (`analysis_goal=debug`) and do not run Yosys/OpenSTA.
- If DebugOptimize applies edits, rerun full runtime chain via RuntimeCTest: Step1a -> Step1b -> Step2 -> Step3.
- Never skip Step2 on optimization reruns.
- Exit optimize loop when DebugOptimize reports no-op/target-reached/blocked, then finalize workflow result.

## DebugOptimize contracts
- Input contract to DebugOptimize: `DEBUG_OPTIMIZE_HANDOFF_V1`
- Output contract from DebugOptimize: `DEBUG_OPTIMIZE_RESULT_V1`
- Conductor should relay runtime evidence and Yosys/OpenSTA summary to support deterministic iteration.

## Required contracts
- Author output contract: `BALL_HANDOFF_V1`
- Registrar output contract: `BALL_REGISTRATION_RESULT_V1`
- Contract templates:
   - `.github/promote/BALL_HANDOFF_V1.template.json`
   - `.github/promote/BALL_REGISTRATION_RESULT_V1.template.json`
- Enforce invariants:
  - `decode.bid == mapping.ballId`
  - `mapping.ballName == ball_name`
  - `ballName == wrapper class simple name`

## Preflight checklist (must print before execution)
- [ ] `arch/src/main/scala/examples/toy/balldomain/DomainDecoder.scala` exists
- [ ] `arch/src/main/scala/examples/toy/balldomain/DISA.scala` exists
- [ ] `arch/src/main/scala/examples/toy/balldomain/bbus/busRegister.scala` exists
- [ ] `.buckyball-rules/01-hw-interface.md` exists
- [ ] `.buckyball-rules/03-ball-registration.md` exists
- [ ] `.buckyball-rules/06-verify-checklist.md` exists

If any rule file is missing, explicitly schedule generation and stop downstream steps until available.

## Trigger phrases for one-shot automation
- Treat user intent as one-shot end-to-end when prompts include words like:
   - “自动调用”, “一键完成”, “端到端”, “全流程”, “自动串联”
- In one-shot mode, execute full chain without pausing: rules check -> author -> registrar -> summary.

## Output format
- Pure Markdown.
- Title: `# Buckyball Multi-Agent Orchestration Plan`
- Sections: `Requirement Plan`, `Stage Decision`, `Preflight`, `Next Agent`, `Blocking Items`.
- No conversational filler.
- Prefer compact contract relay (JSON-only blocks) unless user requests verbose output.

## Completion criteria
- Mark workflow complete only when:
   - both contracts are produced (`BALL_HANDOFF_V1`, `BALL_REGISTRATION_RESULT_V1`), and
   - runtime CTest gate passes.

## Verification alignment
- Default completion gate: runtime CTest checks.
- Optional static checks remain local-development oriented unless user explicitly requests CI parity.

## UI commands reference
- `/agents` for selecting custom workflow agents.
- `/skills` for checking loaded skills.
- `/instructions` for instruction/rule files.
- `/hooks` for hook configuration and diagnostics.
