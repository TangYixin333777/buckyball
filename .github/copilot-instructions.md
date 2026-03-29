# Buckyball Copilot Instructions

## Purpose

This repository uses a handoff-based multi-agent workflow for Ball development.
The coordination model is: Conductor -> Author -> Registrar -> CTest -> RuntimeTest (optional static dry-run).

## Sources of truth

- `.buckyball-rules/01-hw-interface.md`
- `.buckyball-rules/03-ball-registration.md`
- `.buckyball-rules/06-verify-checklist.md`

## Workflow policy

- Use custom agents under `.github/agents` for role-specific behavior.
- Use skills under `.github/skills` as capability packs.
- Use hooks under `.github/hooks` for deterministic enforcement.
- Use handoff templates under `.github/promote` to keep contracts concise and stable.
- Use handoff contracts in chat output:
  - `BALL_HANDOFF_V1`
  - `BALL_REGISTRATION_RESULT_V1`

## Guardrails

- Author stage must not edit registration plane files.
- Registrar stage must not edit prototype Ball implementation files.
- Default completion gate is runtime CTest verification. Static validation is optional dry-run.

## Consistency invariants

- `decode.bid == mapping.ballId`
- `mapping.ballName == ball_name`
- `ballNum == len(ballIdMappings)`
- No duplicate `ballId`
- No duplicate funct7 symbol/value

## Notes

- If tool availability differs across VS Code versions, unavailable tools are ignored.
- Use Chat Diagnostics to verify loaded agents, skills, instructions, and hooks.
