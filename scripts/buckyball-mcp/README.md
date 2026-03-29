# Buckyball MCP Server

MCP server for the Buckyball multi-agent hardware design workflow.
Built with [FastMCP](https://gofastmcp.com/) 3.x (standalone framework).

## Exposed Tools

| Tool | Description |
|---|---|
| `parse_rules` | Inspect required `.buckyball-rules` files and summarize headings |
| `validate_static` | Run static invariant checks for mapping/decode/rule readiness |
| `author_ball` | Plan or apply Ball authoring artifacts (BALL_HANDOFF_V1) |
| `register_ball` | Validate handoff and plan/apply three-plane registration |
| `prepare_ctest` | Plan or apply CTest + ISA registration changes |
| `run_bbdev_test_compile` | Compile software test target in `bb-tests/build` (cmake + ninja) |
| `run_bbdev_workload_build` | Run bbdev workload build (software/workload artifacts) |
| `run_bbdev_verilog` | Run bbdev verilator --verilog for hardware generation |
| `run_bbdev_verilator` | Run bbdev verilator --run for simulation |
| `bbdev_yosys_synth` | Compatibility alias: run Yosys synthesis + OpenSTA timing |
| `run_bbdev_yosys_opensta` | Run bbdev yosys --synth (Yosys synthesis + OpenSTA timing) |
| `summarize_yosys_opensta_reports` | Summarize hierarchy/timing reports for optimization handoff |
| `find_latest_bdb_log` | Find latest `arch/log/*/bdb.ndjson` (fallback: `bdb.log`) |
| `summarize_bdb_log` | Summarize bdb.ndjson (fallback: bdb.log) with pass/fail conclusion |

Notes for Yosys top:
- For Ball top module names, MCP normalizes the first letter to uppercase before invoking bbdev Yosys.
- Example: input top `im2colBall` is normalized to `Im2colBall`.

## Architecture: bbdev HTTP Server

All `bbdev_*` tools communicate with the **bbdev HTTP API server** rather than
shelling out to CLI commands. The MCP server **automatically manages** the bbdev
server lifecycle:

1. On first `bbdev_*` tool call, the server starts `pnpm dev --port <port>` inside
   `$REPO_ROOT/bbdev/api/`, selecting an available port in 5200–5500.
2. Health-checks the server (HTTP GET) for up to 90 seconds.
3. Subsequent calls reuse the running server; if it crashes, it is restarted automatically.
4. On MCP process exit, the bbdev server is terminated via `atexit`.

Server logs are written to `$REPO_ROOT/bbdev/server.log`.

This architecture eliminates the previous issues with `nix develop -c bbdev`
subprocess calls (wrong cwd, missing `flake.nix`, `bbdev` not found, etc.).

## Prompts

| Prompt | Description |
|---|---|
| `bbdev_smoke_test` | Step-by-step guide for an agent to verify all bbdev HTTP tools work |

Prompts are pre-authored conversation starters. Use them to guide an agent
through a multi-step workflow.

## Prerequisites

- Python >= 3.10
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- Node.js + pnpm (required by the bbdev API server at `$REPO_ROOT/bbdev/api/`)

## Install & Run

```bash
cd buckyball-mcp

# Install dependencies
uv sync

# Run the server (stdio transport)
uv run buckyball-mcp
```

Or with `python -m`:

```bash
uv run python -m buckyball_mcp
```

## Configuration

### REPO_ROOT

The server needs to know the Buckyball repository root.
Resolution order:

1. Environment variable `BUCKYBALL_REPO_ROOT` (absolute path, always wins)
2. Auto-detect: walk up from cwd looking for `flake.nix`
3. Fall back to current working directory (`cwd`)

### Debug Logging

Set `BUCKYBALL_MCP_DEBUG=1` to enable debug-level logging to stderr.

## VS Code Integration

Add to `.vscode/mcp.json`:

```json
{
  "servers": {
    "buckyball-mcp": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/buckyball-mcp",
        "run",
        "buckyball-mcp"
      ],
      "env": {
        "BUCKYBALL_REPO_ROOT": "/absolute/path/to/buckyball-repo"
      }
    }
  }
}
```

## Guarded Writes

Tools that modify files support two modes:

- **`mode: "dry-run"`** (default) — return planned operations only
- **`mode: "apply"`** — perform guarded writes, requires `confirm_apply: "I_UNDERSTAND_WRITES"`

## Development

```bash
# Run MCP Inspector for interactive testing
uv run fastmcp dev src/buckyball_mcp/server.py

# Inspect registered tools/resources/prompts
uv run fastmcp inspect src/buckyball_mcp/server.py
```

## Claude Desktop Integration

Install the server directly into Claude Desktop:

```bash
uv run fastmcp install src/buckyball_mcp/server.py --name "Buckyball MCP"
```
