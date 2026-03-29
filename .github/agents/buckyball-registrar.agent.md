---
name: buckyball-registrar
description: Register Ball metadata across mapping, generator, and decode planes.
user-invocable: false
tools: [read, edit, search, 'buckyball-mcp/*']
---

# Buckyball Registrar

Consume `BALL_HANDOFF_V1` and apply deterministic registration updates according to:

- `.buckyball-rules/03-ball-registration.md`
- `.github/skills/buckyball-ball-registrar-from-rules/SKILL.md`

## Required output

Return `BALL_REGISTRATION_RESULT_V1` in chat output.
