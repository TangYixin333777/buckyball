# Buckyball Handoff Templates

This folder provides concise, machine-readable contract templates for the multi-agent handoff flow.

This folder is the single source of truth for handoff contract schema and required fields.

## Files

- `BALL_HANDOFF_V1.template.json`: Author -> Registrar payload.
- `BALL_REGISTRATION_RESULT_V1.template.json`: Registrar -> Conductor payload.
- `contracts.meta.json`: required/optional keys and output policy (`compact` vs `verbose`).
- `BUCKYBALL_MCP_RUNTIME_EXECUTE_V1.prompt.md`: Prompt template for runtime execution flow via MCP tools in apply mode.
- `BUCKYBALL_CONDUCTOR_IM2COL_E2E_V2.prompt.md`: Prompt template for full auto-chain conductor flow (Author -> Registrar -> CTest -> Runtime -> DebugOptimize) focused on im2col.

## Usage

- Keep these templates as the schema source when writing prompts or validating agent output.
- Prefer the minimum required fields to reduce context size and parsing ambiguity.
- For examples with actual values, see `.buckyball-rules/04-ball-author-output.md` and `.buckyball-rules/05-ball-registrar-output.md`.
- Skills and MCP validation should read required keys from `contracts.meta.json` instead of duplicating inline schema blocks.

## BALL_HANDOFF_V1 minimum contract notes

- `isa.op` and `isa.func7` are mandatory and must be explicit.
- `registrar_min` is mandatory and provides minimum fields for deterministic registration:
	- `registrar_min.mapping.{ball_name, ball_id}`
	- `registrar_min.generator.class_name`
	- `registrar_min.decode.{op, func7, bid}`
- Conductor should fail-fast on missing required keys and allow at most one author correction round.
