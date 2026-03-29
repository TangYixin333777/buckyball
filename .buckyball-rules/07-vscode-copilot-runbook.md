# VS Code Copilot Multi-Agent Runbook

## Goal

Run Buckyball tasks with four agent roles:
- Conductor
- Ball Author
- Ball Registrar
- CTest Author
- Runtime Test

## Prerequisites

- Open workspace at `/home/ROXY/Code/buckyball`.
- GitHub Copilot Chat is enabled in VS Code.
- Ensure custom assets are present:
  - custom agents: `.github/agents/*.agent.md`
  - skills: `.github/skills/*/SKILL.md`
  - instructions: `.github/copilot-instructions.md`, `.github/instructions/*.instructions.md`
  - hooks: `.github/hooks/*.json`
  - rules: `.buckyball-rules/*.md`

## Chat customization commands

- `/agents`: inspect and switch custom agents.
- `/skills`: inspect available skills.
- `/instructions`: inspect instruction files and rules.
- `/hooks`: inspect and configure hook commands.

Use `Chat: Open Chat Customizations` to view loaded agents/skills/instructions/hooks in one place.

## Recommended settings keys

Add these entries to workspace settings when custom paths are needed:

- `chat.agentFilesLocations`
- `chat.agentSkillsLocations`
- `chat.instructionsFilesLocations`
- `chat.hookFilesLocations`

Workspace already provides an example in `.vscode/settings.json`.

## Rule readiness checklist

- `.buckyball-rules/00-orchestration.md`
- `.buckyball-rules/01-hw-interface.md`
- `.buckyball-rules/03-ball-registration.md`
- `.buckyball-rules/06-verify-checklist.md`

## Contract source of truth

- `.github/promote/BALL_HANDOFF_V1.template.json`
- `.github/promote/BALL_REGISTRATION_RESULT_V1.template.json`
- `.github/promote/contracts.meta.json`

## MCP server startup

```bash
cd /home/ROXY/Code/buckyball
python3 scripts/mcp/buckyball_mcp_server.py
```

## MCP smoke check

Use a minimal JSON-RPC request to confirm the server can list tools:

```bash
printf 'Content-Length: 46\r\n\r\n{"jsonrpc":"2.0","id":1,"method":"tools/list"}' \
  | python3 scripts/mcp/buckyball_mcp_server.py
```

## Suggested invocation prompts

- Conductor one-shot:
  - `请按 handoff 流程执行：Author -> Registrar -> CTest运行验证；静态校验仅在需要时执行。`
- Author only:
  - `基于 .buckyball-rules/01 和 02 生成一个新 Ball，并输出 BALL_HANDOFF_V1。`
- Registrar only:
  - `消费 BALL_HANDOFF_V1，更新三平面并输出 BALL_REGISTRATION_RESULT_V1。`
- CTest only:
  - `为该 Ball 生成 toy 分组 CTest 并更新 CMake 注册。`
- Runtime test only:
  - `执行 bbdev workload/verilator，并检查最新 bdb.ndjson（回退 bdb.log）给出 PASS/FAIL 结论。`

## Handoff boundaries

- Author -> Registrar:
  - requires valid `BALL_HANDOFF_V1`
  - invariant: `decode.bid == mapping.ballId`
  - template: `.github/promote/BALL_HANDOFF_V1.template.json`
- Registrar -> Static validation:
- Registrar -> Runtime CTest:
  - requires valid `BALL_REGISTRATION_RESULT_V1`
  - executes bbdev build/run and checks latest `bdb.ndjson` (fallback `bdb.log`)
  - template: `.github/promote/BALL_REGISTRATION_RESULT_V1.template.json`
- Runtime CTest -> Optional static validation:
  - optional invariant dry-run stage

## Hooks behavior

- `PreToolUse`: deny dangerous terminal commands and protected hook-path edits.
- `PostToolUse`: inject warnings when required rule files are missing after edits.

## Verification policy

- Default auto-chain completion uses runtime CTest checks.
- Recommended MCP path:
  - `run_bbdev_workload_build`
  - `run_bbdev_verilator`
  - `find_latest_bdb_log`
  - `summarize_bdb_log`
- Optional static dry-run:
  - `validate_static`
- Runtime checks should follow:
  - `nix build`
  - `nix develop -c bbdev workload --build`
  - `nix develop -c bbdev verilator --verilog '--config sims.verilator.BuckyballToyVerilatorConfig'`
  - `nix develop -c bbdev verilator --build '--jobs 16'`
  - optional: `nix develop -c bbdev sardine --run '--workload ctest'`

## Boundaries

- Contracts `BALL_HANDOFF_V1` and `BALL_REGISTRATION_RESULT_V1` are chat outputs by default.
- If persistent artifacts are required, ask agent to write them explicitly.
- Auto chaining is implemented through custom-agent handoffs and subagent delegation, not by implicit platform event scheduling.
