---
name: buckyball-ball-registration-extraction
description: Consume BALL_HANDOFF_V1 from Ball Author Agent and apply Ball registration updates (mapping/generator/decode) for Buckyball toy balldomain.
---

When asked to register a new Ball, act as the **Ball Registrar Agent**. Consume the Ball Author handoff, then apply deterministic registration changes only.

Follow this exact process:

1) Parse required handoff
- Input must contain a JSON block with `handoff_version = BALL_HANDOFF_V1`.
- Required fields source of truth:
  - `.github/promote/contracts.meta.json` -> `contracts.BALL_HANDOFF_V1.required`
- Reject or ask correction if:
  - `decode.bid != mapping.ballId`
  - `mapping.ballName != ball_name`
  - `isa.op` or `isa.func7` is missing
  - `registrar_min` subtree is incomplete
  - `isa.op != registrar_min.decode.op`
  - `isa.func7 != registrar_min.decode.func7`

2) Update mapping plane
- Edit `arch/src/main/scala/framework/balldomain/configs/default.json`:
  - Append or update one `ballIdMappings` entry:
    - `ballId = mapping.ballId`
    - `ballName = mapping.ballName`
    - `inBW = mapping.inBW`
    - `outBW = mapping.outBW`
  - Keep `ballNum` consistent with mapping count.

3) Update generator plane
- Edit `arch/src/main/scala/examples/toy/balldomain/bbus/busRegister.scala`:
  - Add import for the new wrapper class.
  - Add `case "<ballName>" => () => new <ballName>(b)` in match-case.
- Preserve existing style and ordering conventions.

4) Update decode plane
- Edit `arch/src/main/scala/examples/toy/balldomain/DISA.scala`:
  - Add `val <disa_symbol> = BitPat("<funct7>")`.
- Edit `arch/src/main/scala/examples/toy/balldomain/DomainDecoder.scala`:
  - Import or reference the new DISA symbol.
  - Add one ListLookup entry with `BID = mapping.ballId.U`.
  - Use the same field layout convention as existing ops unless handoff explicitly requires custom decode behavior.

5) Validate invariants
- `decode.bid == mapping.ballId`.
- `decode.bid == registrar_min.decode.bid`.
- `mapping.ballName == registrar_min.mapping.ball_name`.
- `ballName` matches wrapper class simple name used in generator match-case.
- No duplicate `ballId` and no duplicate `funct7` symbol in decode table.

6) Output format requirements
- Output pure Markdown only.
- Title must be exactly: `# Buckyball Ball Registration Patch Plan & Result`
- Include sections:
  - `Applied Changes`
  - `Invariant Checks`
  - `Source of truth`
- Include final line: `请将本文保存为 .buckyball-rules/03-ball-registration.md`.

7) Communication contract back to Ball Author Agent
- At end, append JSON block `BALL_REGISTRATION_RESULT_V1`:
- Contract schema source of truth:
  - `.github/promote/BALL_REGISTRATION_RESULT_V1.template.json`
  - `.github/promote/contracts.meta.json` -> `contracts.BALL_REGISTRATION_RESULT_V1.required`
- Do not redefine contract schema inline in this skill.
