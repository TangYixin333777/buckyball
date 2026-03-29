# Buckyball Multi-Agent Orchestration Rules

scope: conductor
source_of_truth:
- .github/skills/buckyball-multi-agent-orchestrator/SKILL.md

## must

- Run in auto-chain mode unless user explicitly requests stage-by-stage mode.
- Implement stage transitions with handoffs between custom agents.
- Use hooks for deterministic policy checks around tool usage.
- Enforce strict stage order:
  1. preflight
  2. rule readiness
  3. ball author
  4. ball registrar
  5. ctest authoring
  6. runtime test execution
  7. optional static validation
- Stop on hard blockers:
  - missing mandatory rule files
  - invalid BALL_HANDOFF_V1
  - invalid BALL_REGISTRATION_RESULT_V1
  - invariant failure
- Use runtime test execution as default completion gate.
- Keep static validation optional as dry-run guardrail.

## forbidden

- Do not run registrar before BALL_HANDOFF_V1 is valid.
- Do not claim workflow complete if any gate failed.
- Do not edit prototype files inside registrar stage.
- Do not edit registration planes inside author stage.
- Do not describe implicit platform auto-wakeup as guaranteed behavior.

## examples

- One-shot trigger phrases:
  - 自动调用
  - 一键完成
  - 端到端
  - 全流程
  - 自动串联
- Required gate invariants:
  - decode.bid == mapping.ballId
  - mapping.ballName == ball_name
  - ballName == wrapper class simple name

## validation

- Preflight paths exist:
  - arch/src/main/scala/examples/toy/balldomain/DomainDecoder.scala
  - arch/src/main/scala/examples/toy/balldomain/DISA.scala
  - arch/src/main/scala/examples/toy/balldomain/bbus/busRegister.scala
  - .buckyball-rules/01-hw-interface.md
  - .buckyball-rules/03-ball-registration.md
  - .buckyball-rules/06-verify-checklist.md
- Author contract and registrar contract both parse as valid JSON blocks.

## failure_cases

- Missing required keys in BALL_HANDOFF_V1: rerun Author stage.
- Duplicate ballId or funct7: fail registrar and require new allocation.
- ballNum mismatch with mapping count: fail optional static validation.
