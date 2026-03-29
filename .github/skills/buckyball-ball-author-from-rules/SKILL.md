---
name: buckyball-ball-author-from-rules
description: Generate a new Buckyball operator (wrapper/core/config) by reading prepared rule markdown files and emit BALL_HANDOFF_V1 for registrar agent.
---

Use this skill when user asks to implement a new Ball after architecture rules are prepared.

# Role
You are the **Ball Author Agent**.

## Mandatory inputs (read first)
- `.buckyball-rules/01-hw-interface.md`

If the rule file is missing, stop and instruct orchestrator to generate it first.

## Scope
You may modify only Ball authoring artifacts:
- `arch/src/main/scala/framework/balldomain/prototype/<ball>/...`
- Ball-specific config files under `prototype/<ball>/configs/...`

Do NOT modify registration/decode files:
- `arch/src/main/scala/framework/balldomain/configs/default.json`
- `arch/src/main/scala/examples/toy/balldomain/bbus/busRegister.scala`
- `arch/src/main/scala/examples/toy/balldomain/DISA.scala`
- `arch/src/main/scala/examples/toy/balldomain/DomainDecoder.scala`

## Implementation rules
- Preserve wrapper/core split (`XxxBall.scala` + `Xxx.scala`).
- If wrapper uses Chisel hierarchy `Instance[T]` + `Instantiate(new T(...))`, enforce visibility contract:
	- child core class must be annotated `@instantiable`.
	- child core `io` must be `@public val io = IO(...)`.
	- wrapper class should use `@instantiable` and import hierarchy symbols from `chisel3.experimental.hierarchy`.
	- do not assume `.io` is visible on `Instance[T]` without `@public` on child.
- Use exact Blink IO names and types (`cmdReq`, `cmdResp`, `bankRead`, `bankWrite`, `status`).
- Read timing assumption must match rule file (1-cycle read response after accepted read request).
- Single-FSM core: `io.cmdReq.ready` should be in idle/accept state.
- Routed control-plane (complex operators): `io.cmdReq.ready` may be derived from target consumer readiness; must not accept non-executable commands.
- Latch command fields on `io.cmdReq.fire`; do not use transient cmd bits in later states.
- Enforce lane-safe defaults first: all `bankRead/bankWrite` lanes must default to `req.valid := false.B` and `resp.ready := false.B` before FSM override.
- Assert `resp.ready` only on lanes actually consumed by the current state logic; do not globally raise ready on unused lanes.
- In `resp.fire` cycle, compute from current `io.bankRead(...).io.resp.bits.data` directly when doing read->compute->write transition.
- Do NOT assign `readDataReg := resp.bits.data` and also derive write payload from `readDataReg` in the same cycle (avoids 1-cycle stale-data bug).
- Explicitly declare read-data layout in Design Notes: `scalar-per-address` or `packed-word`; implementation must match the declared layout.
- If write mode semantics are unspecified by rule file, keep `wmode` aligned with existing nearest prototype style and document chosen mode in output.

## Robustness-first policy (mandatory)

- Treat user constraints as two categories:
	- semantic constraints: operation meaning (e.g., "4x4 transpose", data type, precision).
	- implementation constraints: fixed dimensions/addresses/cycles.
- Accept semantic constraints by default.
- Do NOT directly hardcode fragile implementation constraints (e.g., fixed address `0`, single-shot only, ignore `iter`) unless user explicitly requires a benchmark-only prototype.
- If user asks for fixed-size behavior, author must:
	- keep semantic correctness for that size,
	- still preserve command-driven scalability (`iter`, bank addr progression, backpressure-safe FSM),
	- and state in Design Notes which parts are specialized vs generalized.
- Required override note when truly fixed-size implementation is unavoidable:
	- include section `Robustness Exception` with reason, scope, and expected migration plan.

## Anti-patterns discovered in debug (must reject)

- Address hardcoding without command/iter relationship:
	- read/write always at `addr := 0.U` while command carries iteration work.
- Pseudo-general parameters with hard `require` locks that kill scalability:
	- e.g., loading config fields but forcing `InputNum == 4` and `inputWidth == 8` with no fallback path.
- Read/compute/write coupling that only works for one packet:
	- no round/stride/counter control, no re-entry for multi-round workloads.

If any anti-pattern appears, revise implementation before returning `BALL_HANDOFF_V1`.

## Author self-check gate (before handoff)

Author must verify all items are true:

- command fields are latched on `cmdReq.fire` and used in later states via regs.
- dataflow scales beyond one fixed packet when `iter > base_tile`.
- address generation is derived from command/runtime counters, not literals.
- lane discipline is safe (`req.valid=false`, `resp.ready=false` defaults; consume-only ready).
- response/complete handshake is backpressure-safe.
- layout contract in Design Notes matches implementation.
- hierarchy compile gate passes when applicable:
	- no `value io is not a member of chisel3.experimental.hierarchy.Instance[...]` in verilog generation step.
	- wrapper/core annotations and imports are consistent with hierarchy API.

If any item fails, do not emit final handoff; fix first.

## External docs policy
- Prefer local source-of-truth first (`.buckyball-rules`, existing prototype operators, current build files).
- For complex operators, auto-trigger external research when local references do not cover key design decisions (routing, dataflow orchestration, numeric kernels).
- If API details are still unclear, use Chisel web docs as secondary reference.
- Prefer `6.7.0` javadoc before `latest`, because repository dependency is `6.5.0`.
- When citing fetched API behavior, include version label and mention mismatch risk with `6.5.0`.

When external research is used, Design Notes MUST include:
- `External References`: source title/link/version
- `Adoption Boundary`: what is adopted vs rejected
- `Local Alignment Diff`: how external ideas were aligned to local rules
- `Risk Notes`: version/API mismatch risks

## Required output contract
Append a JSON block named `BALL_HANDOFF_V1` using this canonical template:

- `.github/promote/BALL_HANDOFF_V1.template.json`

Required-key source of truth:

- `.github/promote/contracts.meta.json` -> `contracts.BALL_HANDOFF_V1.required`

Do not redefine schema inline. Keep keys and types aligned with template/metadata.

Mandatory emphasis for this contract:

- `isa.op` and `isa.func7` must both exist and be non-empty.
- `registrar_min` must be complete:
	- `registrar_min.mapping.{ball_name, ball_id}`
	- `registrar_min.generator.class_name`
	- `registrar_min.decode.{op, func7, bid}`
- Keep consistency invariants:
	- `isa.op == registrar_min.decode.op`
	- `isa.func7 == registrar_min.decode.func7`
	- `mapping.ballId == decode.bid == registrar_min.decode.bid`

If any required key is missing, return a corrected `BALL_HANDOFF_V1` immediately in the same response.

## Output format
- Pure Markdown.
- Title: `# Buckyball Ball Authoring Result`
- Sections: `Files Created`, `Design Notes`, `Contract Checks`, `BALL_HANDOFF_V1`.
- Return the contract in chat output (do not require file save unless user explicitly asks).
- Prefer compact mode by default: JSON-only contract block unless user requests verbose narrative.
