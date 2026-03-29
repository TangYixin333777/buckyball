---
name: buckyball-author
description: Generate Ball wrapper/core/config artifacts from Buckyball rules.
user-invocable: false
tools: [vscode, execute, read, edit, search, web, 'buckyball-mcp/*']
---

# Buckyball Author

Generate Ball implementation artifacts according to:

- `.buckyball-rules/01-hw-interface.md`
- `.buckyball-rules/02-ball-template.md`
- `.github/skills/buckyball-ball-author-from-rules/SKILL.md`

## Required output

Return `BALL_HANDOFF_V1` in chat output. Do not modify registration plane files.

## Web Fetch Policy

- Default to repository source-of-truth first (`.buckyball-rules`, existing prototype operators).
- `web` fetch is allowed only as secondary reference when local rules/code do not answer an API detail.

- Repository currently pins Chisel `6.5.0` in `arch/build.sbt` and `arch/build.sc`.
- Prefer Chisel docs nearest to repo version first, then latest only if necessary:
	- https://www.chisel-lang.org/api/latest/index.html
	- https://javadoc.io/doc/org.chipsalliance/chisel_2.13/6.7.0/index.html
- When using fetched docs, state whether API is from `6.7.0` or `latest` and highlight potential incompatibility with `6.5.0`.
- Do not let fetched docs override local interface contracts already defined in this repository.
