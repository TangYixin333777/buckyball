---
name: buckyball-hw-interface-extraction
description: Extract strict hardware interface (Blink & BBus) specifications and configuration patterns for Buckyball Operators (Balls). Use this when asked to document or extract hardware interface specs.
---

When asked to extract or document the Buckyball hardware interface and configuration specifications, conduct a rigorous analysis of the hardware interface and configuration source code within the current workspace.

Follow this exact process to build the ground truth specification:

1) Analyze Structural Separation
- Examine `arch/src/main/scala/framework/balldomain/prototype/*` (especially `ReluBall.scala` vs `Relu.scala`, `TransposeBall.scala` vs `Transpose.scala`).
- Explain the split:
	- `XXBall.scala`: Blink-facing wrapper (instantiate core, connect `cmdReq/cmdResp/bankRead/bankWrite/status`, derive bandwidth from `ballIdMappings`).
	- `XX.scala`: core compute/state machine and memory access behavior.

2) Inspect Parameterization & IO (code-first, no invented names)
- Analyze:
	- `arch/src/main/scala/framework/balldomain/configs/BallDomainParam.scala`
	- `arch/src/main/scala/framework/balldomain/configs/default.json`
	- `arch/src/main/scala/framework/balldomain/prototype/*/configs/*Param.scala`
- Use actual interfaces from `blink/blink.scala` and `blink/bank.scala`:
	- `BlinkIO`: `cmdReq`, `cmdResp`, `bankRead`, `bankWrite`, `status`
	- `BankRead` / `BankWrite`: metadata (`bank_id`, `rob_id`, `ball_id`, `group_id`) + `io` (`SramReadIO` / `SramWriteIO`)
- Describe how `ballIdMappings.inBW/outBW`, `memDomain.bankNum`, `memDomain.bankWidth`, `memDomain.bankMaskLen`, `memDomain.bankEntries` determine Vec lengths and bit widths.
- Do NOT reference non-existent abstractions (e.g., `BaseBall`, `BankCtrlIO`, `BankDataIO`, `cmd/bank_ctrl/bank_data`) unless they exist in current code.

3) Detail Bank Read/Write Protocol with exact signal names
- Use:
	- `arch/src/main/scala/framework/memdomain/backend/banks/SramIO.scala`
	- `arch/src/main/scala/framework/memdomain/backend/banks/SramBank.scala`
- Extract exact request/response fields:
	- Read req: `addr`; read resp: `data`
	- Write req: `addr`, `mask`, `data`, `wmode`; write resp: `ok`
- Explain handshake semantics via Decoupled (`valid/ready/fire`).
- CRITICAL: State read latency strictly from code path (`SyncReadMem` + `resp.valid := RegNext(ren)`), i.e. request fire to response valid latency. Do not guess.
- Include channel-usage discipline in extracted spec:
	- all lanes default safe (`req.valid=false`, `resp.ready=false`)
	- only consumed lanes may assert `resp.ready`
	- explain single-lane vs multi-lane consumption behavior explicitly
- Include payload layout contract in extracted spec:
	- classify data movement as `scalar-per-address` or `packed-word`
	- describe required consistency between declared layout and bit-slicing/read-address logic

4) Document Status/FSM Semantics correctly
- Extract top-level status definition from `blink/status.scala` (`BallStatus` with `idle` and `running` only).
- Clarify that canonical FSM enum is implemented inside each core (`Relu.scala`, `Transpose.scala`, etc.), not in `blink/status.scala`.
- Explain required mapping from internal FSM to `io.status.idle/running`.

5) Explain BBus Integration and registration requirements
- Analyze:
	- `arch/src/main/scala/framework/balldomain/bbus/cmdrouter/CmdRouter.scala`
	- `arch/src/main/scala/framework/balldomain/bbus/memrouter/memRouter.scala`
	- `arch/src/main/scala/examples/toy/balldomain/bbus/busRegister.scala`
	- `arch/src/main/scala/examples/toy/balldomain/DomainDecoder.scala`
	- `arch/src/main/scala/examples/toy/balldomain/DISA.scala`
	- `arch/src/main/scala/framework/balldomain/rs/reservationStation.scala`
- State clearly:
	- Command dispatch uses `cmd.bid` and ball idle gating.
	- MemRouter multiplexes channels by configured `inBW/outBW` and dynamic mapping tables.
	- New Ball registration includes **three planes** for this codebase:
		1. mapping plane: `ballIdMappings` in `framework/balldomain/configs/default.json`
		2. generator plane: `examples/toy/balldomain/bbus/busRegister.scala` match-case
		3. decode plane: opcode in `DISA.scala` + decode entry in `DomainDecoder.scala` (`BID` must equal `ballId`)
	- `ballName` must match wrapper class simple name because BBus connects channels via `ball.getClass.getSimpleName` lookup.

6) Output format requirements
- Output pure Markdown only.
- Title must be exactly: `# Buckyball Hardware Interface & Config Specification`
- No conversational filler.
- Include a final line: `请将本文保存为 .buckyball-rules/01-hw-interface.md`.
- Include a compact “Source of truth” section listing every analyzed file path.

7) Multi-agent decoupling guidance
- When user asks for multi-agent workflow, split architecture content into:
	- **Ball Author Agent scope**: wrapper/core/config + `BALL_HANDOFF_V1` handoff block.
	- **Ball Registrar Agent scope**: mapping/generator/decode registration updates.
- If registration strategy is uncertain, output 2-3 explicit options (e.g., match-case registry vs table-driven registry), each with exact impacted files and compatibility notes.
- Always include a “Contract Invariants” section with at least:
	- `decode.bid == ballIdMappings.ballId`
	- `ballName == wrapper class simple name`
	- `inBW/outBW` consistent across config, wrapper IO and MemRouter aggregation assumptions.
