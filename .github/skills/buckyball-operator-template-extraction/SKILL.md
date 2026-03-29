---
name: buckyball-operator-template-extraction
description: Extract strict hardware development guidelines and a complete Chisel template for Buckyball operators (Balls). Use this when asked to extract or generate a standard Ball template.
---

When asked to extract or document the development guidelines and template for a Buckyball operator (Ball), deeply analyze the standard hardware operators in the arch/src/main/scala/framework/balldomain/prototype/ directory (e.g., relu/ReluBall.scala, transpose/TransposeBall.scala).

Follow this exact process to generate the "Buckyball Strict Operator (Ball) Development Bible & Boilerplate":

1) Define Mandatory Boilerplate & IO from real code
- Analyze references:
	- `arch/src/main/scala/framework/balldomain/prototype/relu/ReluBall.scala`
	- `arch/src/main/scala/framework/balldomain/prototype/relu/Relu.scala`
	- `arch/src/main/scala/framework/balldomain/prototype/transpose/TransposeBall.scala`
	- `arch/src/main/scala/framework/balldomain/prototype/transpose/Transpose.scala`
	- `arch/src/main/scala/framework/balldomain/blink/blink.scala`
	- `arch/src/main/scala/framework/balldomain/blink/bank.scala`
- Use `GlobalConfig` injection pattern (`class XxxBall(val b: GlobalConfig)`) and `BlinkIO(b, inBW, outBW)`.
- Use exact IO names and types:
	- `cmdReq: Flipped(Decoupled(new BallRsIssue(b)))`
	- `cmdResp: Decoupled(new BallRsComplete(b))`
	- `bankRead: Vec(inBW, Flipped(new BankRead(b)))`
	- `bankWrite: Vec(outBW, Flipped(new BankWrite(b)))`
	- `status: new BallStatus`
- Do NOT output obsolete/non-existent interfaces (`cmd`, `bank_ctrl`, `bank_data`, `we`).

2) Establish FSM & control-flow rules (derived, not fabricated)
- Present a recommended FSM structure based on existing operators (Idle/Read/Compute/Write/Complete or similar).
- Enforce practical safety rules used in code:
	- `io.cmdReq.ready` asserted in idle/accepting state only.
	- Latch command fields needed after issue into regs on `io.cmdReq.fire`.
	- Avoid depending on transient `io.cmdReq.bits` in later states.
	- All lanes default safe (`req.valid=false`, `resp.ready=false`) before state overrides.
	- Assert `resp.ready` only on lanes consumed by the active state logic.
- Keep rule wording accurate: classify as “recommended robust pattern from existing designs,” unless universally enforced by shared trait/module.

3) Map dataflow & memory timing with exact SRAM protocol
- Source of truth:
	- `arch/src/main/scala/framework/memdomain/backend/banks/SramIO.scala`
	- `arch/src/main/scala/framework/memdomain/backend/banks/SramBank.scala`
- State exact fields and handshake:
	- Read: `req(addr)` / `resp(data)`
	- Write: `req(addr, data, mask, wmode)` / `resp(ok)`
- Explicitly restate read latency from code (`resp.valid := RegNext(req.fire)`): one cycle from accepted read request to valid response.
- Add a mandatory data-layout clause in generated guide/template:
	- state whether the Ball is `scalar-per-address` or `packed-word`
	- ensure read/write logic matches the declared layout
	- require explicit note when diverging from `Relu`/`Transpose` packed-word slicing style

4) Synthesize compilable template
- Output a fully closed, copyable `TemplateBall.scala` with no `???`.
- Must include:
	- package/imports
	- `TemplateBall` wrapper + core `Template`
	- config case class/object loading `default.json`
	- command latching regs
	- counters
	- example Read -> Compute -> Write pipeline
	- status driving (`idle/running`) and completion path back to idle
- Keep naming/API consistent with current codebase conventions.

5) Output format requirements
- Output pure Markdown only.
- Title must be exactly: `# Buckyball Strict Operator (Ball) Development Guide & Template`
- No conversational filler.
- Include final line: `请将本文保存为 .buckyball-rules/01-hw-interface.md`.
- Include a short “Source of truth” file list.

6) Multi-agent decoupling contract (Ball Author -> Ball Registrar)
- This skill is the **Ball Author Agent** side only. It must NOT directly modify decode/register files unless explicitly requested.
- It MUST append a machine-readable JSON block at the end of output so a registration agent can consume it.
- The block header must be exactly `BALL_HANDOFF_V1`.
- Contract schema source of truth:
	- `.github/promote/BALL_HANDOFF_V1.template.json`
	- `.github/promote/contracts.meta.json` -> `contracts.BALL_HANDOFF_V1.required`
- Do not redefine contract schema inline in this skill.

- Required consistency checks before emitting handoff:
	- `mapping.ballName` equals wrapper class simple name (e.g. `FooBall`).
	- `decode.bid == mapping.ballId`.
	- `inBW/outBW` match wrapper/core IO Vec sizes.
