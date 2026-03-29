"""Buckyball MCP Server — multi-agent hardware design workflow tools.

Tools exposed:
  parse_rules, validate_static, author_ball, register_ball,
        prepare_ctest, run_bbdev_test_compile, run_bbdev_workload_build, run_bbdev_verilog,
      run_bbdev_verilator, bbdev_yosys_synth, run_bbdev_yosys_opensta,
      summarize_yosys_opensta_reports,
  find_latest_bdb_log, summarize_bdb_log

Transport: stdio (default)

Supports safe planning via mode=dry-run (default) and guarded writes
via mode=apply + confirm_apply="I_UNDERSTAND_WRITES".
"""

from __future__ import annotations
from fastmcp import FastMCP
import json
import logging
import os
import re
import shutil
import subprocess
import time
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import httpx

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger = logging.getLogger("buckyball-mcp")
if os.environ.get("BUCKYBALL_MCP_DEBUG", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}:
    logging.basicConfig(level=logging.DEBUG, format="[buckyball-mcp] %(message)s")

# ---------------------------------------------------------------------------
# FastMCP instance
# ---------------------------------------------------------------------------
mcp = FastMCP("buckyball-mcp")

# ---------------------------------------------------------------------------
# Configuration — REPO_ROOT resolved from env, or auto-detected by walking
# up from cwd until a directory containing flake.nix (or .git) is found.
# ---------------------------------------------------------------------------


def _detect_repo_root() -> Path:
    """Return the Buckyball repo root directory.

    Resolution order:
      1. ``BUCKYBALL_REPO_ROOT`` env var (explicit, always wins)
      2. Walk up from cwd looking for ``flake.nix`` — the canonical marker
         for the Buckyball mono-repo.
      3. Fall back to cwd if nothing is found.
    """
    env = os.environ.get("BUCKYBALL_REPO_ROOT", "").strip()
    if env:
        return Path(env).resolve()

    cursor = Path.cwd().resolve()
    for parent in [cursor, *cursor.parents]:
        if (parent / "flake.nix").exists():
            return parent
    # last resort
    return cursor


REPO_ROOT: Path = _detect_repo_root()

RULE_DIR = REPO_ROOT / ".buckyball-rules"
PROMOTE_DIR = REPO_ROOT / ".github" / "promote"
CONTRACT_META_PATH = PROMOTE_DIR / "contracts.meta.json"
APPLY_CONFIRM_TOKEN = "I_UNDERSTAND_WRITES"

AUTHOR_PREFIX = Path("arch/src/main/scala/framework/balldomain/prototype")
AUTHOR_CONFIG_PREFIX = AUTHOR_PREFIX
REGISTRATION_FILES = {
    Path("arch/src/main/scala/framework/balldomain/configs/default.json"),
    Path("arch/src/main/scala/examples/toy/balldomain/bbus/busRegister.scala"),
    Path("arch/src/main/scala/examples/toy/balldomain/DISA.scala"),
    Path("arch/src/main/scala/examples/toy/balldomain/DomainDecoder.scala"),
}
CTEST_PREFIX = Path("bb-tests/workloads/src/CTest")
ARCH_LOG_DIR = REPO_ROOT / "arch" / "log"
BDB_NDJSON_NAME = "bdb.ndjson"
BDB_TEXT_NAME = "bdb.log"
MAX_CAPTURE_CHARS = 1200
MAX_OUTPUT_EXCERPT_LINES = 12
MAX_HIGHLIGHT_LINES = 8
NIX_DEVELOP_WARMED = False

# ===================================================================== #
#                         Helper functions                                #
# ===================================================================== #


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _ok(payload: Any) -> str:
    """Serialize *payload* to a JSON string for tool return."""
    return json.dumps(payload, ensure_ascii=True, indent=2)


def _resolve_mode(mode: str) -> str:
    mode = mode.strip().lower()
    if mode not in {"dry-run", "apply"}:
        return "invalid"
    return mode


def _is_apply_confirmed(confirm_apply: str) -> bool:
    return confirm_apply == APPLY_CONFIRM_TOKEN


def _relative_path(path: Path) -> Path:
    absolute = path if path.is_absolute() else (REPO_ROOT / path)
    return absolute.resolve().relative_to(REPO_ROOT)


def _write_text(path: Path, content: str, *, overwrite: bool = False) -> Dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        return {
            "path": str(_relative_path(path)),
            "status": "skipped",
            "reason": "exists",
        }
    before = path.read_text(encoding="utf-8") if path.exists() else None
    if before == content:
        return {
            "path": str(_relative_path(path)),
            "status": "unchanged",
        }
    path.write_text(content, encoding="utf-8")
    return {
        "path": str(_relative_path(path)),
        "status": "written",
    }


def _set_mode_result(mode: str, *, dry_run: Dict[str, Any], apply_fn: Any) -> str:
    """Return JSON string for dry-run or apply result, raise on invalid mode."""
    if mode == "invalid":
        raise ValueError("Invalid mode. Use 'dry-run' or 'apply'.")
    if mode == "dry-run":
        payload = dict(dry_run)
        payload["mode"] = "dry-run"
        return _ok(payload)
    result = apply_fn()
    payload = dict(result)
    payload["mode"] = "apply"
    return _ok(payload)


def _repo_path_from_param(path_value: str) -> Path:
    candidate = Path(path_value)
    absolute = candidate if candidate.is_absolute() else (REPO_ROOT / candidate)
    resolved = absolute.resolve()
    resolved.relative_to(REPO_ROOT)
    return resolved


# ---------------------------------------------------------------------------
# CTest helpers
# ---------------------------------------------------------------------------


def _ensure_ctest_registration(
    cmake_text: str, test_name: str, source_file: str, *, update_build_all_depends: bool
) -> Tuple[str, bool, bool]:
    registration = f"add_cross_platform_test_target({test_name} {source_file})"
    registration_written = False
    depends_written = False

    if registration not in cmake_text:
        anchor = "# Create master build target"
        if anchor in cmake_text:
            cmake_text = cmake_text.replace(anchor, registration + "\n" + anchor, 1)
        else:
            cmake_text += "\n" + registration + "\n"
        registration_written = True

    if update_build_all_depends and f"  {test_name}\n" not in cmake_text:
        target_anchor = "add_custom_target(buckyball-CTest-build ALL DEPENDS"
        comment_anchor = '  COMMENT "Building all workloads for Buckyball"'
        start = cmake_text.find(target_anchor)
        comment = cmake_text.find(comment_anchor, start if start >= 0 else 0)
        if start >= 0 and comment >= 0:
            cmake_text = (
                cmake_text[:comment] + f"  {test_name}\n" + cmake_text[comment:]
            )
            depends_written = True

    return cmake_text, registration_written, depends_written


def _ensure_isa_include(isa_h_text: str, include_line: str) -> Tuple[str, bool]:
    if include_line in isa_h_text:
        return isa_h_text, False
    marker = "#endif // BUCKYBALL_ISA_H"
    if marker in isa_h_text:
        return isa_h_text.replace(marker, include_line + "\n\n" + marker, 1), True
    return isa_h_text + "\n" + include_line + "\n", True


def _generate_ctest_source(test_name: str, isa_op: str) -> str:
    return f"""#include "buckyball.h"
#include <bbhw/isa/isa.h>
#include <bbhw/mem/mem.h>
#include <stdio.h>
#include <stdlib.h>

int main(void) {{
#ifdef MULTICORE
  multicore(MULTICORE);
#endif
  printf("{test_name}: TODO implement workload body and call bb_{isa_op}()\\n");
#ifdef MULTICORE
  exit(0);
#endif
  return 0;
}}
"""


def _generate_isa_source(isa_op: str, isa_func7: int) -> str:
    macro = f"BB_{isa_op.upper()}_FUNC7"
    return f"""#ifndef _BB_{isa_op.upper()}_H_
#define _BB_{isa_op.upper()}_H_

#include "isa.h"

#define {macro} {isa_func7}

// TODO: adjust rs1/rs2 field packing to match decode contract for this Ball.
#define bb_{isa_op}(op1_bank_id, wr_bank_id, iter) \\
  BUCKYBALL_INSTRUCTION_R_R( \\
      (BB_BANK0(op1_bank_id) | BB_BANK2(wr_bank_id) | BB_RD0 | BB_WR), \\
      (FIELD(iter, 0, 9)), \\
      {macro})

#endif // _BB_{isa_op.upper()}_H_
"""


# ---------------------------------------------------------------------------
# Template adaptation helpers
# ---------------------------------------------------------------------------


def _replace_word_variants(text: str, old: str, new: str) -> str:
    if not old or old == new:
        return text
    pairs = [
        (old, new),
        (old.lower(), new.lower()),
        (old.upper(), new.upper()),
        (old.capitalize(), new.capitalize()),
    ]
    for src, dst in pairs:
        text = re.sub(rf"\b{re.escape(src)}\b", dst, text)
    return text


def _adapt_test_template_content(
    content: str, src_symbol: str, dst_symbol: str, test_name: str
) -> str:
    content = _replace_word_variants(content, src_symbol, dst_symbol)
    if src_symbol:
        content = re.sub(
            rf"\bbb_{re.escape(src_symbol)}\b", f"bb_{dst_symbol}", content
        )
    content = re.sub(r"ctest_[a-zA-Z0-9_]+", test_name, content)
    return content


def _adapt_isa_template_content(
    content: str, src_symbol: str, dst_symbol: str, isa_func7: int
) -> str:
    upper_dst = dst_symbol.upper()
    content = re.sub(r"_BB_[A-Z0-9_]+_H_", f"_BB_{upper_dst}_H_", content)
    content = re.sub(r"BB_[A-Z0-9_]+_FUNC7", f"BB_{upper_dst}_FUNC7", content)
    if src_symbol:
        content = re.sub(
            rf"\bbb_{re.escape(src_symbol)}\b", f"bb_{dst_symbol}", content
        )
    content = _replace_word_variants(content, src_symbol, dst_symbol)
    content = re.sub(
        r"(#define\s+BB_[A-Z0-9_]+_FUNC7\s+)\d+", rf"\g<1>{isa_func7}", content
    )
    return content


# ---------------------------------------------------------------------------
# Subprocess / quiescence helpers
# ---------------------------------------------------------------------------


def _trim_text(text: str, limit: int = MAX_CAPTURE_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 80] + "\n...[truncated]...\n" + text[-40:]


def _line_count(text: str) -> int:
    if not text:
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def _extract_tail_lines(text: str, max_lines: int = MAX_OUTPUT_EXCERPT_LINES) -> str:
    if not text:
        return ""
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    return "\n".join(lines[-max_lines:])


def _extract_error_highlights(
    stderr: str, stdout: str, max_lines: int = MAX_HIGHLIGHT_LINES
) -> List[str]:
    pattern = re.compile(
        r"error|failed|exception|traceback|timeout|fatal|trap|segmentation",
        flags=re.IGNORECASE,
    )
    hits: List[str] = []
    for line in stderr.splitlines():
        if pattern.search(line):
            hits.append(line.strip())
            if len(hits) >= max_lines:
                return hits
    for line in stdout.splitlines():
        if pattern.search(line):
            hits.append(line.strip())
            if len(hits) >= max_lines:
                break
    return hits


def _build_output_summary(stdout: str, stderr: str) -> Dict[str, int]:
    return {
        "stdout_chars": len(stdout),
        "stderr_chars": len(stderr),
        "stdout_lines": _line_count(stdout),
        "stderr_lines": _line_count(stderr),
    }


def _default_singlecore_binary_name(test_target: str) -> str:
    return f"{test_target}_singlecore-baremetal"


def _normalize_runtime_binary_name(binary_name: str) -> Tuple[str, bool]:
    value = binary_name.strip()
    if not value:
        return value, False
    if value.endswith("_singlecore-baremetal") or value.endswith(
        "_multicore-baremetal"
    ):
        return value, False
    if value.startswith("ctest_"):
        return f"{value}_singlecore-baremetal", True
    return value, False


def _normalize_verilator_run_args(
    run_args: str,
) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Normalize --binary in run args to avoid common metadata/ELF mismatch.

    Rule:
      - If binary looks like ctest_* without *_singlecore-baremetal/*_multicore-baremetal,
        rewrite to *_singlecore-baremetal.
    """
    pattern = re.compile(r"--binary(?:\s+|=)(\"[^\"]+\"|'[^']+'|[^\s]+)")
    match = pattern.search(run_args)
    if not match:
        return run_args, None

    token = match.group(1)
    quote = ""
    raw_value = token
    if (token.startswith('"') and token.endswith('"')) or (
        token.startswith("'") and token.endswith("'")
    ):
        quote = token[0]
        raw_value = token[1:-1]

    normalized_value, changed = _normalize_runtime_binary_name(raw_value)
    if not changed:
        return run_args, None

    replacement = f"{quote}{normalized_value}{quote}" if quote else normalized_value
    start, end = match.span(1)
    normalized_args = run_args[:start] + replacement + run_args[end:]
    return (
        normalized_args,
        {
            "field": "binary_name",
            "before": raw_value,
            "after": normalized_value,
            "reason": "normalized_missing_baremetal_suffix",
        },
    )


def _run_command(command: List[str], *, timeout_sec: int = 3600) -> Dict[str, Any]:
    def _pack_result(
        *,
        return_code: int,
        stdout_text: str,
        stderr_text: str,
        timed_out: bool = False,
    ) -> Dict[str, Any]:
        ok = (return_code == 0) and not timed_out
        output_summary = _build_output_summary(stdout_text, stderr_text)
        stdout_tail = _trim_text(_extract_tail_lines(stdout_text))
        stderr_tail = _trim_text(_extract_tail_lines(stderr_text))
        highlights = _extract_error_highlights(stderr_text, stdout_text)

        result: Dict[str, Any] = {
            "ok": ok,
            "return_code": return_code,
            "command": " ".join(command),
            "output_summary": output_summary,
            "stdout_excerpt": stdout_tail,
            "stderr_excerpt": stderr_tail,
            "error_highlights": highlights,
            "stdout_omitted": ok,
            "stderr_omitted": False,
        }

        if not ok:
            # Keep compatibility for consumers expecting stdout/stderr keys on failures.
            result["stdout"] = _trim_text(stdout_text)
            result["stderr"] = _trim_text(stderr_text)

        if timed_out:
            result["timeout"] = True

        return result

    try:
        proc = subprocess.run(
            command,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
        return _pack_result(
            return_code=proc.returncode,
            stdout_text=proc.stdout,
            stderr_text=proc.stderr,
        )
    except subprocess.TimeoutExpired as exc:
        return _pack_result(
            return_code=-1,
            stdout_text=exc.stdout or "",
            stderr_text=(exc.stderr or "") + "\nTimeoutExpired",
            timed_out=True,
        )


def _tree_signature(path: Path) -> Tuple[int, int, int]:
    if not path.exists():
        return (0, 0, 0)
    file_count = 0
    total_size = 0
    max_mtime_ns = 0
    for p in path.rglob("*"):
        try:
            if p.is_file():
                st = p.stat()
                file_count += 1
                total_size += int(st.st_size)
                max_mtime_ns = max(max_mtime_ns, int(st.st_mtime_ns))
        except OSError:
            continue
    return (file_count, total_size, max_mtime_ns)


def _wait_for_quiescence(
    path: Path,
    *,
    stable_window_sec: int = 30,
    max_wait_sec: int = 600,
    sample_sec: int = 5,
) -> Dict[str, Any]:
    if max_wait_sec <= 0:
        return {
            "path": str(_relative_path(path)) if path.exists() else str(path),
            "observed": False,
            "stable": False,
            "reason": "max_wait_sec<=0",
            "waited_sec": 0,
        }

    start = time.monotonic()
    last_sig = _tree_signature(path)
    stable_for = 0
    observed = path.exists()

    while True:
        elapsed = int(time.monotonic() - start)
        if elapsed >= max_wait_sec:
            return {
                "path": str(_relative_path(path)) if path.exists() else str(path),
                "observed": observed,
                "stable": False,
                "reason": "max_wait_reached",
                "waited_sec": elapsed,
                "last_signature": {
                    "file_count": last_sig[0],
                    "total_size": last_sig[1],
                    "max_mtime_ns": last_sig[2],
                },
            }

        time.sleep(max(1, sample_sec))
        current_sig = _tree_signature(path)
        observed = observed or path.exists()
        if current_sig == last_sig:
            stable_for += max(1, sample_sec)
            if stable_for >= stable_window_sec:
                return {
                    "path": str(_relative_path(path)) if path.exists() else str(path),
                    "observed": observed,
                    "stable": True,
                    "reason": "stable_window_reached",
                    "waited_sec": int(time.monotonic() - start),
                    "last_signature": {
                        "file_count": current_sig[0],
                        "total_size": current_sig[1],
                        "max_mtime_ns": current_sig[2],
                    },
                }
        else:
            last_sig = current_sig
            stable_for = 0


def _bbdev_command(base_args: List[str], *, use_nix: bool = False) -> List[str]:
    if use_nix:
        return ["nix", "develop", "-c", "bbdev", *base_args]
    return ["bbdev", *base_args]


def _ensure_nix_develop_initialized(timeout_sec: int = 1200) -> Dict[str, Any]:
    global NIX_DEVELOP_WARMED  # noqa: PLW0603
    if NIX_DEVELOP_WARMED:
        return {"ok": True, "skipped": True, "reason": "already_warmed"}

    if shutil.which("nix") is None:
        return {
            "ok": False,
            "reason": "Command not found: nix",
            "hint": "Install nix or provide environment where nix is available.",
        }

    warmup_cmd = ["nix", "develop", "-c", "true"]
    warmup_result = _run_command(warmup_cmd, timeout_sec=timeout_sec)
    if warmup_result.get("ok"):
        NIX_DEVELOP_WARMED = True
    warmup_result["warmup"] = True
    return warmup_result


# ---------------------------------------------------------------------------
# Log helpers
# ---------------------------------------------------------------------------


def _resolve_bdb_artifact_in_dir(log_dir: Path) -> Optional[Path]:
    ndjson_path = log_dir / BDB_NDJSON_NAME
    if ndjson_path.exists():
        return ndjson_path
    text_path = log_dir / BDB_TEXT_NAME
    if text_path.exists():
        return text_path
    return None


def _candidate_log_dirs(filter_token: Optional[str] = None) -> List[Path]:
    if not ARCH_LOG_DIR.exists():
        return []
    dirs = [
        p
        for p in ARCH_LOG_DIR.iterdir()
        if p.is_dir() and _resolve_bdb_artifact_in_dir(p) is not None
    ]
    if filter_token:
        token = filter_token.lower()
        dirs = [d for d in dirs if token in d.name.lower()]
    dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return dirs


def _latest_bdb_log(filter_token: Optional[str] = None) -> Optional[Path]:
    dirs = _candidate_log_dirs(filter_token)
    if not dirs:
        return None
    return _resolve_bdb_artifact_in_dir(dirs[0])


# ---------------------------------------------------------------------------
# Rule / contract helpers
# ---------------------------------------------------------------------------


def _required_rule_paths() -> List[Path]:
    return [
        RULE_DIR / "00-orchestration.md",
        RULE_DIR / "01-hw-interface.md",
        RULE_DIR / "03-ball-registration.md",
        RULE_DIR / "06-verify-checklist.md",
    ]


def _get_by_dotted_path(data: Dict[str, Any], dotted_path: str) -> Any:
    current: Any = data
    for part in dotted_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _load_contract_meta() -> Dict[str, Any]:
    if not CONTRACT_META_PATH.exists():
        return {
            "contracts": {
                "BALL_HANDOFF_V1": {
                    "required": [
                        "handoff_version",
                        "ball_name",
                        "core_name",
                        "package",
                        "mapping.ballId",
                        "mapping.ballName",
                        "mapping.inBW",
                        "mapping.outBW",
                        "decode.disa_symbol",
                        "decode.funct7",
                        "decode.bid",
                        "decode.needs_op2",
                        "decode.iter_from",
                        "files.wrapper",
                        "files.core",
                        "files.config_scala",
                        "files.config_json",
                        "constraints.class_name_must_equal_ballName",
                        "constraints.bid_must_equal_ballId",
                    ]
                },
                "BALL_REGISTRATION_RESULT_V1": {
                    "required": [
                        "result_version",
                        "ball_name",
                        "mapping_applied",
                        "generator_applied",
                        "decode_applied",
                        "touched_files",
                        "errors",
                    ]
                },
            }
        }
    try:
        meta = _read_json(CONTRACT_META_PATH)
        if not isinstance(meta, dict):
            return {}
        return meta
    except Exception:
        return {}


def _required_keys(contract_name: str) -> List[str]:
    meta = _load_contract_meta()
    contracts = meta.get("contracts", {}) if isinstance(meta, dict) else {}
    contract = contracts.get(contract_name, {}) if isinstance(contracts, dict) else {}
    required = contract.get("required", []) if isinstance(contract, dict) else []
    if not isinstance(required, list):
        return []
    return [str(k) for k in required]


def _missing_required_fields(payload: Dict[str, Any], required: List[str]) -> List[str]:
    missing: List[str] = []
    for key in required:
        value = _get_by_dotted_path(payload, key)
        if value is None:
            missing.append(key)
    return missing


# ---------------------------------------------------------------------------
# DISA / registration helpers
# ---------------------------------------------------------------------------


def _extract_bitpat_values(disa_text: str) -> List[int]:
    vals: List[int] = []
    for match in re.finditer(r'BitPat\("b([01]{7})"\)', disa_text):
        vals.append(int(match.group(1), 2))
    return vals


def _max_disa_value(disa_text: str) -> int:
    values = _extract_bitpat_values(disa_text)
    return max(values) if values else -1


def _iter_and_special_expr(iter_from: str) -> Tuple[str, str]:
    if iter_from == "rs2[9:0]":
        return "rs2(9, 0)", "rs2(63, 10)"
    if iter_from == "fixed_zero":
        return "DITER", "rs2(63, 0)"
    return "DITER", "rs2(63, 0)"


def _update_default_json(
    default_json_path: Path, mapping: Dict[str, Any]
) -> Dict[str, Any]:
    cfg = _read_json(default_json_path)
    mappings = cfg.get("ballIdMappings", [])

    if not isinstance(mappings, list):
        raise ValueError("default.json ballIdMappings must be an array")

    ball_id = int(mapping["ballId"])
    for entry in mappings:
        if int(entry.get("ballId", -1)) == ball_id:
            raise ValueError(f"ballId already exists: {ball_id}")

    expected_next = (
        max((int(entry.get("ballId", -1)) for entry in mappings), default=-1) + 1
    )
    if ball_id != expected_next:
        raise ValueError(
            f"ballId must be strict increment. expected={expected_next}, got={ball_id}"
        )

    mappings.append(
        {
            "ballId": ball_id,
            "ballName": str(mapping["ballName"]),
            "inBW": int(mapping["inBW"]),
            "outBW": int(mapping["outBW"]),
        }
    )
    cfg["ballNum"] = len(mappings)
    cfg["ballIdMappings"] = mappings
    default_json_path.write_text(
        json.dumps(cfg, ensure_ascii=True, indent=2) + "\n", encoding="utf-8"
    )
    return {"path": str(_relative_path(default_json_path)), "status": "written"}


def _update_bus_register(
    bus_register_path: Path, ball_name: str, package: str
) -> Dict[str, Any]:
    text = bus_register_path.read_text(encoding="utf-8")

    import_stmt = f"import {package}.{ball_name}"
    if import_stmt not in text:
        anchor = "import framework.balldomain.prototype.im2col.Im2colBall"
        if anchor in text:
            text = text.replace(anchor, anchor + "\n" + import_stmt)
        else:
            text = import_stmt + "\n" + text

    case_stmt = f'case "{ball_name}"'
    if case_stmt not in text:
        anchor = 'case "Im2colBall"    => () => new Im2colBall(b)'
        insertion = f'          case "{ball_name}"    => () => new {ball_name}(b)'
        if anchor in text:
            text = text.replace(anchor, anchor + "\n" + insertion)
        else:
            text = text.replace(
                'case name            => throw new IllegalArgumentException(s"Unknown ball name: $name")',
                insertion
                + "\n"
                + '          case name            => throw new IllegalArgumentException(s"Unknown ball name: $name")',
            )

    bus_register_path.write_text(text, encoding="utf-8")
    return {"path": str(_relative_path(bus_register_path)), "status": "written"}


def _update_disa(disa_path: Path, disa_symbol: str, funct7: str) -> Dict[str, Any]:
    text = disa_path.read_text(encoding="utf-8")
    new_line = f'  val {disa_symbol} = BitPat("{funct7}")'
    if new_line in text:
        return {"path": str(_relative_path(disa_path)), "status": "unchanged"}

    if f'BitPat("{funct7}")' in text:
        raise ValueError(f"funct7 already exists in DISA: {funct7}")
    if f"val {disa_symbol} =" in text:
        raise ValueError(f"DISA symbol already exists: {disa_symbol}")

    max_value = _max_disa_value(text)
    requested_value = int(funct7[1:], 2) if funct7.startswith("b") else -1
    if requested_value != max_value + 1:
        raise ValueError(
            f"funct7 must be strict increment. expected b{max_value + 1:07b}, got {funct7}"
        )

    text = text.replace("}\n", new_line + "\n}\n")
    disa_path.write_text(text, encoding="utf-8")
    return {"path": str(_relative_path(disa_path)), "status": "written"}


def _update_domain_decoder(
    domain_decoder_path: Path, handoff: Dict[str, Any]
) -> Dict[str, Any]:
    text = domain_decoder_path.read_text(encoding="utf-8")
    mapping = handoff["mapping"]
    decode = handoff["decode"]

    disa_symbol = str(decode["disa_symbol"])
    ball_id = int(mapping["ballId"])
    needs_op2 = bool(decode.get("needs_op2", False))
    iter_expr, special_expr = _iter_and_special_expr(
        str(decode.get("iter_from", "rs2[9:0]"))
    )

    new_row = (
        f"      {disa_symbol}      -> List(Y, {'Y' if needs_op2 else 'N'}, Y, Y, "
        f"{'Y' if needs_op2 else 'N'}, "
        f"rs1(7, 0), {'rs1(15, 8)' if needs_op2 else 'DADDR'}, rs1(23, 16), "
        f"{iter_expr}, {ball_id}.U, {special_expr})"
    )

    if f"{disa_symbol}      ->" in text:
        return {"path": str(_relative_path(domain_decoder_path)), "status": "unchanged"}

    marker = "    )\n  )"
    if marker not in text:
        raise ValueError(
            "Failed to find decode table insertion marker in DomainDecoder.scala"
        )

    text = text.replace(marker, ",\n" + new_row + "\n" + marker, 1)
    domain_decoder_path.write_text(text, encoding="utf-8")
    return {"path": str(_relative_path(domain_decoder_path)), "status": "written"}


# ===================================================================== #
#                         MCP Tool definitions                            #
# ===================================================================== #


@mcp.tool()
def parse_rules() -> str:
    """Inspect required .buckyball-rules files and summarize headings."""
    missing = [
        str(p.relative_to(REPO_ROOT)) for p in _required_rule_paths() if not p.exists()
    ]
    sections: Dict[str, List[str]] = {}

    for path in _required_rule_paths():
        if not path.exists():
            continue
        headings: List[str] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("#"):
                headings.append(line.strip())
        sections[str(path.relative_to(REPO_ROOT))] = headings

    return _ok({"missing": missing, "headings": sections})


@mcp.tool()
def validate_static(handoff: Optional[dict] = None) -> str:
    """Run static invariant checks for mapping/decode/rule readiness."""
    default_json = (
        REPO_ROOT / "arch/src/main/scala/framework/balldomain/configs/default.json"
    )
    disa_scala = REPO_ROOT / "arch/src/main/scala/examples/toy/balldomain/DISA.scala"

    if not default_json.exists() or not disa_scala.exists():
        raise ValueError(
            "Missing registration source-of-truth files for static validation."
        )

    cfg = _read_json(default_json)
    mappings = cfg.get("ballIdMappings", [])

    ids = [entry.get("ballId") for entry in mappings]
    id_duplicates = sorted({x for x in ids if ids.count(x) > 1})
    id_is_strict_increment = ids == list(range(len(ids)))

    disa_values = _extract_bitpat_values(disa_scala.read_text(encoding="utf-8"))
    disa_duplicates = sorted({x for x in disa_values if disa_values.count(x) > 1})

    checks: Dict[str, bool] = {
        "ball_num_matches_count": cfg.get("ballNum") == len(mappings),
        "ball_id_unique": len(id_duplicates) == 0,
        "ball_id_strict_increment": id_is_strict_increment,
        "funct7_unique": len(disa_duplicates) == 0,
        "required_rules_present": all(path.exists() for path in _required_rule_paths()),
    }

    handoff_missing: List[str] = []
    if isinstance(handoff, dict):
        handoff_missing = _missing_required_fields(
            handoff, _required_keys("BALL_HANDOFF_V1")
        )
        checks["handoff_required_keys_present"] = len(handoff_missing) == 0
        mapping = handoff.get("mapping", {})
        decode = handoff.get("decode", {})
        checks["handoff_bid_matches_mapping"] = decode.get("bid") == mapping.get(
            "ballId"
        )
        checks["handoff_ballname_matches"] = handoff.get("ball_name") == mapping.get(
            "ballName"
        )

    passed = all(checks.values())
    payload = {
        "passed": passed,
        "checks": checks,
        "details": {
            "id_duplicates": id_duplicates,
            "funct7_duplicates": disa_duplicates,
            "handoff_missing_required": handoff_missing,
        },
    }
    return _ok(payload)


@mcp.tool()
def author_ball(
    ball_name: str = "<XxxBall>",
    core_name: str = "",
    package: str = "",
    mode: str = "dry-run",
    confirm_apply: str = "",
    overwrite: bool = False,
) -> str:
    """Plan or apply Ball authoring artifacts and output expected BALL_HANDOFF_V1 fields."""
    if not core_name:
        core_name = ball_name.replace("Ball", "")
    if not package:
        package = f"framework.balldomain.prototype.{core_name.lower()}"
    resolved_mode = _resolve_mode(mode)

    target_dir = REPO_ROOT / AUTHOR_PREFIX / core_name.lower()
    config_dir = target_dir / "configs"

    wrapper_path = target_dir / f"{ball_name}.scala"
    core_path = target_dir / f"{core_name}.scala"
    config_scala_path = config_dir / f"{ball_name}Param.scala"
    config_json_path = config_dir / "default.json"

    dry_run = {
        "ball_name": ball_name,
        "core_name": core_name,
        "package": package,
        "next_files": [
            str(_relative_path(wrapper_path)),
            str(_relative_path(core_path)),
            str(_relative_path(config_scala_path)),
            str(_relative_path(config_json_path)),
        ],
        "contract": "BALL_HANDOFF_V1",
        "apply_requirements": {
            "confirm_apply": APPLY_CONFIRM_TOKEN,
            "overwrite": "optional bool, default false",
        },
    }

    def _do_apply() -> Dict[str, Any]:
        if not _is_apply_confirmed(confirm_apply):
            return {
                "applied": False,
                "reason": "confirm_apply token missing",
                "required_token": APPLY_CONFIRM_TOKEN,
            }

        wrapper_content = f"""package {package}

import chisel3._
import chisel3.experimental.hierarchy.{{Instance, Instantiate, instantiable, public}}
import framework.balldomain.blink.{{BlinkIO, HasBlink}}
import framework.top.GlobalConfig

@instantiable
class {ball_name}(val b: GlobalConfig) extends Module with HasBlink {{
  private val mapping = b.ballDomain.ballIdMappings
    .find(_.ballName == "{ball_name}")
    .getOrElse(throw new IllegalArgumentException("{ball_name} not found in config"))

  @public
  val io = IO(new BlinkIO(b, mapping.inBW, mapping.outBW))
  def blink: BlinkIO = io

  val core: Instance[{core_name}] = Instantiate(new {core_name}(b))
  core.io.cmdReq <> io.cmdReq
  core.io.cmdResp <> io.cmdResp
  for (i <- 0 until mapping.inBW) {{ core.io.bankRead(i) <> io.bankRead(i) }}
  for (i <- 0 until mapping.outBW) {{ core.io.bankWrite(i) <> io.bankWrite(i) }}
  io.status <> core.io.status
}}
"""

        core_content = f"""package {package}

import chisel3._
import chisel3.experimental.hierarchy.{{instantiable, public}}
import framework.balldomain.blink.{{BallStatus, BankRead, BankWrite}}
import framework.balldomain.rs.{{BallRsComplete, BallRsIssue}}
import framework.top.GlobalConfig

@instantiable
class {core_name}(val b: GlobalConfig) extends Module {{
  private val mapping = b.ballDomain.ballIdMappings
    .find(_.ballName == "{ball_name}")
    .getOrElse(throw new IllegalArgumentException("{ball_name} not found in config"))

  @public
  val io = IO(new Bundle {{
    val cmdReq = Flipped(Decoupled(new BallRsIssue(b)))
    val cmdResp = Decoupled(new BallRsComplete(b))
    val bankRead = Vec(mapping.inBW, Flipped(new BankRead(b)))
    val bankWrite = Vec(mapping.outBW, Flipped(new BankWrite(b)))
    val status = new BallStatus
  }})

    // Skeleton only: fill FSM/dataflow with .buckyball-rules/01-hw-interface.md.
  io.cmdReq.ready := false.B
  io.cmdResp.valid := false.B
  io.cmdResp.bits.rob_id := 0.U
  io.status.idle := true.B
  io.status.running := false.B

  for (i <- 0 until mapping.inBW) {{
    io.bankRead(i).io.req.valid := false.B
    io.bankRead(i).io.req.bits.addr := 0.U
    io.bankRead(i).io.resp.ready := false.B
    io.bankRead(i).bank_id := 0.U
    io.bankRead(i).rob_id := 0.U
    io.bankRead(i).ball_id := 0.U
    io.bankRead(i).group_id := 0.U
  }}

  for (i <- 0 until mapping.outBW) {{
    io.bankWrite(i).io.req.valid := false.B
    io.bankWrite(i).io.req.bits.addr := 0.U
    io.bankWrite(i).io.req.bits.data := 0.U
    io.bankWrite(i).io.req.bits.mask := VecInit(Seq.fill(b.memDomain.bankMaskLen)(0.U(1.W)))
    io.bankWrite(i).io.req.bits.wmode := false.B
    io.bankWrite(i).io.resp.ready := false.B
    io.bankWrite(i).bank_id := 0.U
    io.bankWrite(i).rob_id := 0.U
    io.bankWrite(i).ball_id := 0.U
    io.bankWrite(i).group_id := 0.U
  }}
}}
"""

        config_scala_content = f"""package {package}.configs

import upickle.default._

case class {ball_name}Param(InputNum: Int, inputWidth: Int)

object {ball_name}Param {{
  implicit val rw: ReadWriter[{ball_name}Param] = macroRW

  def apply(): {ball_name}Param = {{
    val jsonStr = scala.io.Source
      .fromFile("src/main/scala/framework/balldomain/prototype/{core_name.lower()}/configs/default.json")
      .mkString
    read[{ball_name}Param](jsonStr)
  }}
}}
"""

        config_json_content = '{\n  "InputNum": 16,\n  "inputWidth": 8\n}\n'

        writes = [
            _write_text(wrapper_path, wrapper_content, overwrite=overwrite),
            _write_text(core_path, core_content, overwrite=overwrite),
            _write_text(config_scala_path, config_scala_content, overwrite=overwrite),
            _write_text(config_json_path, config_json_content, overwrite=overwrite),
        ]
        return {
            "applied": True,
            "writes": writes,
            "overwrite": overwrite,
        }

    return _set_mode_result(resolved_mode, dry_run=dry_run, apply_fn=_do_apply)


@mcp.tool()
def register_ball(
    handoff: dict,
    mode: str = "dry-run",
    confirm_apply: str = "",
) -> str:
    """Validate handoff and plan/apply three-plane registration file updates."""
    if not isinstance(handoff, dict):
        raise ValueError(
            "register_ball requires 'handoff' object with BALL_HANDOFF_V1 fields."
        )
    resolved_mode = _resolve_mode(mode)

    missing = _missing_required_fields(handoff, _required_keys("BALL_HANDOFF_V1"))
    if missing:
        raise ValueError(
            "Contract violation: missing required BALL_HANDOFF_V1 keys: "
            + ", ".join(missing)
        )

    mapping = handoff.get("mapping", {})
    decode = handoff.get("decode", {})
    if decode.get("bid") != mapping.get("ballId"):
        raise ValueError("Contract violation: decode.bid must equal mapping.ballId.")

    ball_name = handoff.get("ball_name")
    ball_name_mapping = mapping.get("ballName")
    if ball_name != ball_name_mapping:
        raise ValueError("Contract violation: ball_name must equal mapping.ballName.")

    dry_run = {
        "contract": "BALL_REGISTRATION_RESULT_V1",
        "touched_files": [str(path) for path in sorted(REGISTRATION_FILES)],
        "ball_name": ball_name,
        "apply_requirements": {
            "confirm_apply": APPLY_CONFIRM_TOKEN,
        },
    }

    def _do_apply() -> Dict[str, Any]:
        if not _is_apply_confirmed(confirm_apply):
            return {
                "applied": False,
                "reason": "confirm_apply token missing",
                "required_token": APPLY_CONFIRM_TOKEN,
            }

        pkg = str(handoff.get("package", "")).strip()
        if not pkg:
            return {
                "applied": False,
                "reason": "handoff.package is required for generator import",
            }

        default_json = (
            REPO_ROOT / "arch/src/main/scala/framework/balldomain/configs/default.json"
        )
        bus_register = (
            REPO_ROOT
            / "arch/src/main/scala/examples/toy/balldomain/bbus/busRegister.scala"
        )
        disa = REPO_ROOT / "arch/src/main/scala/examples/toy/balldomain/DISA.scala"
        domain_decoder = (
            REPO_ROOT
            / "arch/src/main/scala/examples/toy/balldomain/DomainDecoder.scala"
        )

        updates = []
        updates.append(_update_default_json(default_json, mapping))
        updates.append(_update_bus_register(bus_register, str(ball_name), pkg))
        updates.append(
            _update_disa(disa, str(decode["disa_symbol"]), str(decode["funct7"]))
        )
        updates.append(_update_domain_decoder(domain_decoder, handoff))
        return {
            "applied": True,
            "updates": updates,
            "result_version": "BALL_REGISTRATION_RESULT_V1",
            "ball_name": ball_name,
        }

    return _set_mode_result(resolved_mode, dry_run=dry_run, apply_fn=_do_apply)


@mcp.tool()
def prepare_ctest(
    group: str = "toy",
    test_name: str = "ctest_new_ball_test",
    source_file: str = "",
    isa_op: str = "",
    isa_func7: Optional[int] = None,
    isa_file: str = "",
    isa_include: str = "",
    isa_h_path: str = "bb-tests/workloads/lib/bbhw/isa/isa.h",
    update_isa: bool = True,
    update_build_all_depends: bool = True,
    test_template: str = "",
    isa_template: str = "",
    template_symbol: str = "",
    binary_name: str = "",
    mode: str = "dry-run",
    confirm_apply: str = "",
    overwrite: bool = False,
) -> str:
    """Plan or apply CTest + ISA registration changes, with optional template-based semantic adaptation."""
    resolved_mode = _resolve_mode(mode)

    if not source_file:
        source_file = f"{test_name}.c"
    if not isa_op:
        isa_op = test_name.replace("ctest_", "").replace("_test", "")
    isa_op = isa_op.strip()
    test_template = test_template.strip()
    isa_template = isa_template.strip()
    template_symbol = template_symbol.strip()

    ctest_dir = CTEST_PREFIX / group
    source_path = ctest_dir / source_file
    cmake_path = ctest_dir / "CMakeLists.txt"
    isa_h_path_obj = Path(isa_h_path)

    isa_file_default = (
        f"{isa_func7}_{isa_op}.c" if isinstance(isa_func7, int) else f"{isa_op}.c"
    )
    if not isa_file:
        isa_file = isa_file_default
    isa_file = isa_file.strip()
    isa_path = isa_h_path_obj.parent / isa_file
    if not isa_include:
        isa_include = f'#include "{isa_file}"'
    isa_include = isa_include.strip()

    template_symbol_resolved = template_symbol
    if not template_symbol_resolved and test_template:
        template_symbol_resolved = Path(test_template).stem.replace("_test", "")
    if not template_symbol_resolved and isa_template:
        tmpl_name = Path(isa_template).stem
        template_symbol_resolved = (
            tmpl_name.split("_", 1)[1] if "_" in tmpl_name else tmpl_name
        )

    dry_run = {
        "group": group,
        "files": [
            str(source_path),
            str(cmake_path),
            str(isa_path),
            str(isa_h_path_obj),
        ],
        "commands": [
            "nix develop -c bbdev workload --build",
            "nix develop -c bbdev verilator --run "
            "'--config sims.verilator.BuckyballToyVerilatorConfig --binary <binary_name>'",
        ],
        "apply_requirements": {
            "confirm_apply": APPLY_CONFIRM_TOKEN,
            "binary_name": "optional; defaults to <test_name>_singlecore-baremetal",
            "test_template": "optional repo path; if set, copy template source content",
            "isa_template": "optional repo path; if set, copy ISA template content",
            "template_symbol": "optional source op token in template; default auto-detected",
        },
        "isa_registration": {
            "update_isa": update_isa,
            "isa_file": isa_file,
            "isa_include": isa_include,
            "update_build_all_depends": update_build_all_depends,
        },
    }

    def _do_apply() -> Dict[str, Any]:
        if not _is_apply_confirmed(confirm_apply):
            return {
                "applied": False,
                "reason": "confirm_apply token missing",
                "required_token": APPLY_CONFIRM_TOKEN,
            }

        resolved_binary = (
            binary_name.strip()
            if binary_name.strip()
            else _default_singlecore_binary_name(test_name)
        )
        normalized_binary, binary_changed = _normalize_runtime_binary_name(
            resolved_binary
        )
        resolved_binary = normalized_binary

        if test_template:
            source_content = _repo_path_from_param(test_template).read_text(
                encoding="utf-8"
            )
            source_content = _adapt_test_template_content(
                source_content, template_symbol_resolved, isa_op, test_name
            )
        else:
            source_content = _generate_ctest_source(test_name, isa_op)

        writes = [
            _write_text(REPO_ROOT / source_path, source_content, overwrite=overwrite)
        ]

        cmake_abs = REPO_ROOT / cmake_path
        if not cmake_abs.exists():
            return {
                "applied": False,
                "reason": f"Missing CMake file: {cmake_path}",
                "writes": writes,
            }

        cmake_text = cmake_abs.read_text(encoding="utf-8")
        cmake_text, registration_written, depends_written = _ensure_ctest_registration(
            cmake_text,
            test_name,
            source_file,
            update_build_all_depends=update_build_all_depends,
        )
        if registration_written or depends_written:
            cmake_abs.write_text(cmake_text, encoding="utf-8")
            writes.append({"path": str(cmake_path), "status": "written"})
        else:
            writes.append({"path": str(cmake_path), "status": "unchanged"})

        isa_h_abs = REPO_ROOT / isa_h_path_obj
        if update_isa:
            if not isa_h_abs.exists():
                return {
                    "applied": False,
                    "reason": f"Missing ISA header: {isa_h_path_obj}",
                    "writes": writes,
                }

            isa_abs = REPO_ROOT / isa_path
            if isa_template:
                if not isinstance(isa_func7, int):
                    return {
                        "applied": False,
                        "reason": "isa_func7 is required when isa_template is provided",
                        "writes": writes,
                    }
                isa_content = _repo_path_from_param(isa_template).read_text(
                    encoding="utf-8"
                )
                isa_content = _adapt_isa_template_content(
                    isa_content, template_symbol_resolved, isa_op, isa_func7
                )
            else:
                if not isinstance(isa_func7, int):
                    return {
                        "applied": False,
                        "reason": "isa_func7 is required when isa_template is not provided",
                        "writes": writes,
                    }
                isa_content = _generate_isa_source(isa_op, isa_func7)

            writes.append(_write_text(isa_abs, isa_content, overwrite=overwrite))

            isa_h_text = isa_h_abs.read_text(encoding="utf-8")
            new_isa_h_text, isa_written = _ensure_isa_include(isa_h_text, isa_include)
            if isa_written:
                isa_h_abs.write_text(new_isa_h_text, encoding="utf-8")
                writes.append({"path": str(isa_h_path_obj), "status": "written"})
            else:
                writes.append({"path": str(isa_h_path_obj), "status": "unchanged"})

        return {
            "applied": True,
            "writes": writes,
            "test_target": test_name,
            "binary_name": resolved_binary,
            "binary_name_normalized": binary_changed,
            "isa_registration": {
                "update_isa": update_isa,
                "isa_file": str(isa_path),
                "isa_include": isa_include,
                "update_build_all_depends": update_build_all_depends,
            },
        }

    return _set_mode_result(resolved_mode, dry_run=dry_run, apply_fn=_do_apply)


@mcp.tool()
def run_bbdev_test_compile(
    test_target: str,
    mode: str = "dry-run",
    use_nix: bool = True,
    timeout_sec: int = 3600,
    build_dir: str = "bb-tests/build",
    quiescence_max_wait_sec: int = 600,
    quiescence_stable_window_sec: int = 30,
    quiescence_sample_sec: int = 5,
) -> str:
    """Run Step 1a compile in bb-tests/build (cmake + ninja <test_target>)."""
    resolved_mode = _resolve_mode(mode)
    target = test_target.strip()
    if not target:
        raise ValueError(
            "run_bbdev_test_compile requires non-empty 'test_target', "
            "e.g. ctest_relu_test"
        )
    if not re.fullmatch(r"[A-Za-z0-9_.+-]+", target):
        raise ValueError("test_target contains unsupported characters")

    build_dir_path = _repo_path_from_param(build_dir)
    rel_build_dir = str(build_dir_path.relative_to(REPO_ROOT))
    compile_script = (
        f"cd {rel_build_dir} && "
        f"rm -rf * && "
        f"cmake -G Ninja ../ && "
        f"ninja {target}"
    )
    if use_nix:
        cmd = ["nix", "develop", "-c", "bash", "-lc", compile_script]
    else:
        cmd = ["bash", "-lc", compile_script]

    dry_run = {
        "command": " ".join(cmd),
        "timeout_sec": timeout_sec,
        "notes": "Compile software test target in bb-tests/build before workload build.",
        "build_dir": rel_build_dir,
        "test_target": target,
        "quiescence": {
            "path": rel_build_dir,
            "max_wait_sec": quiescence_max_wait_sec,
            "stable_window_sec": quiescence_stable_window_sec,
            "sample_sec": quiescence_sample_sec,
        },
    }

    def _do_apply() -> Dict[str, Any]:
        if use_nix:
            warmup_result = _ensure_nix_develop_initialized(
                timeout_sec=min(timeout_sec, 1200)
            )
            if not warmup_result.get("ok"):
                return {
                    "ok": False,
                    "reason": "Failed to initialize nix develop environment",
                    "warmup": warmup_result,
                }
        else:
            warmup_result = {
                "ok": True,
                "skipped": True,
                "reason": "use_nix=false",
            }

        executable = cmd[0]
        if shutil.which(executable) is None:
            return {
                "ok": False,
                "reason": f"Command not found: {executable}",
                "hint": "Enable environment where required toolchain is available, or set use_nix=true.",
                "warmup": warmup_result,
            }

        result = _run_command(cmd, timeout_sec=timeout_sec)
        result["warmup"] = warmup_result
        result["build_dir"] = rel_build_dir
        result["test_target"] = target
        if result.get("ok"):
            result["quiescence"] = _wait_for_quiescence(
                build_dir_path,
                max_wait_sec=quiescence_max_wait_sec,
                stable_window_sec=quiescence_stable_window_sec,
                sample_sec=quiescence_sample_sec,
            )
        return result

    return _set_mode_result(resolved_mode, dry_run=dry_run, apply_fn=_do_apply)


@mcp.tool()
def run_bbdev_workload_build(
    mode: str = "dry-run",
    use_nix: bool = True,
    timeout_sec: int = 3600,
    quiescence_path: str = "bb-tests/build",
    quiescence_max_wait_sec: int = 600,
    quiescence_stable_window_sec: int = 30,
    quiescence_sample_sec: int = 5,
) -> str:
    """Run bbdev workload build in dry-run/apply modes."""
    resolved_mode = _resolve_mode(mode)
    cmd = _bbdev_command(["workload", "--build"], use_nix=use_nix)
    q_path = Path(quiescence_path)

    dry_run = {
        "command": " ".join(cmd),
        "timeout_sec": timeout_sec,
        "notes": "Run workload build before verilator run. A one-time `nix develop -c true` warmup is executed before runtime commands.",
        "quiescence": {
            "path": str(q_path),
            "max_wait_sec": quiescence_max_wait_sec,
            "stable_window_sec": quiescence_stable_window_sec,
            "sample_sec": quiescence_sample_sec,
        },
    }

    def _do_apply() -> Dict[str, Any]:
        warmup_result = _ensure_nix_develop_initialized(
            timeout_sec=min(timeout_sec, 1200)
        )
        if not warmup_result.get("ok"):
            return {
                "ok": False,
                "reason": "Failed to initialize nix develop environment",
                "warmup": warmup_result,
            }

        executable = cmd[0]
        if shutil.which(executable) is None:
            return {
                "ok": False,
                "reason": f"Command not found: {executable}",
                "hint": "Enable environment where bbdev is available, or set use_nix=true.",
                "warmup": warmup_result,
            }
        result = _run_command(cmd, timeout_sec=timeout_sec)
        result["warmup"] = warmup_result
        if result.get("ok"):
            result["quiescence"] = _wait_for_quiescence(
                REPO_ROOT / q_path,
                max_wait_sec=quiescence_max_wait_sec,
                stable_window_sec=quiescence_stable_window_sec,
                sample_sec=quiescence_sample_sec,
            )
        return result

    return _set_mode_result(resolved_mode, dry_run=dry_run, apply_fn=_do_apply)


@mcp.tool()
def run_bbdev_verilog(
    config: str = "sims.verilator.BuckyballToyVerilatorConfig",
    mode: str = "dry-run",
    use_nix: bool = True,
    timeout_sec: int = 3600,
    quiescence_path: str = "arch/build",
    quiescence_max_wait_sec: int = 600,
    quiescence_stable_window_sec: int = 30,
    quiescence_sample_sec: int = 5,
) -> str:
    """Run bbdev verilator --verilog with supplied config in dry-run/apply modes."""
    resolved_mode = _resolve_mode(mode)
    config = config.strip()

    if not config:
        raise ValueError(
            "run_bbdev_verilog requires non-empty 'config', "
            "e.g. sims.verilator.BuckyballToyVerilatorConfig"
        )

    cmd = _bbdev_command(
        ["verilator", "--verilog", f"--config {config}"], use_nix=use_nix
    )
    q_path = Path(quiescence_path)
    harness_path = REPO_ROOT / "arch" / "build" / "obj_dir" / "VTestHarness"

    dry_run = {
        "command": " ".join(cmd),
        "timeout_sec": timeout_sec,
        "notes": "Generate Verilog/build artifacts before simulation run. "
        "A one-time `nix develop -c true` warmup is executed before runtime commands.",
        "quiescence": {
            "path": str(q_path),
            "max_wait_sec": quiescence_max_wait_sec,
            "stable_window_sec": quiescence_stable_window_sec,
            "sample_sec": quiescence_sample_sec,
        },
        "harness_check": {
            "path": str(harness_path.relative_to(REPO_ROOT)),
            "phase": "post_verilog",
        },
    }

    def _do_apply() -> Dict[str, Any]:
        warmup_result = _ensure_nix_develop_initialized(
            timeout_sec=min(timeout_sec, 1200)
        )
        if not warmup_result.get("ok"):
            return {
                "ok": False,
                "reason": "Failed to initialize nix develop environment",
                "warmup": warmup_result,
            }

        executable = cmd[0]
        if shutil.which(executable) is None:
            return {
                "ok": False,
                "reason": f"Command not found: {executable}",
                "hint": "Enable environment where bbdev is available, or set use_nix=true.",
                "warmup": warmup_result,
            }
        result = _run_command(cmd, timeout_sec=timeout_sec)
        result["warmup"] = warmup_result
        if result.get("ok"):
            result["quiescence"] = _wait_for_quiescence(
                REPO_ROOT / q_path,
                max_wait_sec=quiescence_max_wait_sec,
                stable_window_sec=quiescence_stable_window_sec,
                sample_sec=quiescence_sample_sec,
            )
        result["harness_check"] = {
            "path": str(harness_path.relative_to(REPO_ROOT)),
            "exists": harness_path.exists(),
            "phase": "post_verilog",
        }
        return result

    return _set_mode_result(resolved_mode, dry_run=dry_run, apply_fn=_do_apply)


@mcp.tool()
def run_bbdev_verilator(
    run_args: str,
    mode: str = "dry-run",
    use_nix: bool = True,
    timeout_sec: int = 5400,
    log_filter: str = "",
    quiescence_path: str = "arch/log",
    quiescence_max_wait_sec: int = 600,
    quiescence_stable_window_sec: int = 30,
    quiescence_sample_sec: int = 5,
) -> str:
    """Run bbdev verilator --run with supplied run_args in dry-run/apply modes."""
    resolved_mode = _resolve_mode(mode)
    run_args = run_args.strip()

    if not run_args:
        raise ValueError(
            "run_bbdev_verilator requires 'run_args' string, "
            "e.g. --jobs 16 --binary <bin> --config ... --batch"
        )

    normalized_run_args, binary_normalization = _normalize_verilator_run_args(run_args)
    cmd = _bbdev_command(["verilator", "--run", normalized_run_args], use_nix=use_nix)
    q_path = Path(quiescence_path)

    dry_run = {
        "command": " ".join(cmd),
        "binary_normalization": binary_normalization,
        "timeout_sec": timeout_sec,
        "notes": "This command should generate a new arch/log/<timestamp>-*/bdb.ndjson artifact (or compatible bdb.log). "
        "A one-time `nix develop -c true` warmup is executed before runtime commands.",
        "new_log_required": True,
        "quiescence": {
            "path": str(q_path),
            "max_wait_sec": quiescence_max_wait_sec,
            "stable_window_sec": quiescence_stable_window_sec,
            "sample_sec": quiescence_sample_sec,
        },
    }

    def _do_apply() -> Dict[str, Any]:
        filter_tok = log_filter.strip() or None
        pre_latest_log = _latest_bdb_log(filter_tok)
        pre_latest_log_rel = (
            str(pre_latest_log.relative_to(REPO_ROOT)) if pre_latest_log else None
        )
        pre_latest_log_mtime = (
            pre_latest_log.stat().st_mtime_ns
            if pre_latest_log and pre_latest_log.exists()
            else None
        )

        warmup_result = _ensure_nix_develop_initialized(
            timeout_sec=min(timeout_sec, 1200)
        )
        if not warmup_result.get("ok"):
            return {
                "ok": False,
                "reason": "Failed to initialize nix develop environment",
                "warmup": warmup_result,
            }

        executable = cmd[0]
        if shutil.which(executable) is None:
            return {
                "ok": False,
                "reason": f"Command not found: {executable}",
                "hint": "Enable environment where bbdev is available, or set use_nix=true.",
                "warmup": warmup_result,
            }
        result = _run_command(cmd, timeout_sec=timeout_sec)
        result["warmup"] = warmup_result
        if binary_normalization is not None:
            result["binary_normalization"] = binary_normalization
        if result.get("ok"):
            result["quiescence"] = _wait_for_quiescence(
                REPO_ROOT / q_path,
                max_wait_sec=quiescence_max_wait_sec,
                stable_window_sec=quiescence_stable_window_sec,
                sample_sec=quiescence_sample_sec,
            )

        post_latest_log = _latest_bdb_log(filter_tok)
        post_latest_log_rel = (
            str(post_latest_log.relative_to(REPO_ROOT)) if post_latest_log else None
        )
        post_latest_log_mtime = (
            post_latest_log.stat().st_mtime_ns
            if post_latest_log and post_latest_log.exists()
            else None
        )

        generated_new_log = False
        if post_latest_log is not None:
            generated_new_log = (
                pre_latest_log is None or post_latest_log != pre_latest_log
            )
            if (
                not generated_new_log
                and pre_latest_log_mtime is not None
                and post_latest_log_mtime is not None
                and post_latest_log_mtime > pre_latest_log_mtime
            ):
                generated_new_log = True

        result["pre_latest_bdb_log"] = pre_latest_log_rel
        result["post_latest_bdb_log"] = post_latest_log_rel
        result["generated_new_log"] = generated_new_log
        result["latest_bdb_log"] = post_latest_log_rel if generated_new_log else None
        result["stale_latest_bdb_log"] = (
            post_latest_log_rel if not generated_new_log else None
        )

        # Guard against false success where simulation run did not produce a new log.
        if result.get("ok") and not generated_new_log:
            result["ok"] = False
            result["failure_class"] = "RUNTIME_ENV_OR_INFRA"
            result["reason"] = (
                "run_bbdev_verilator completed without generating a new bdb artifact (bdb.ndjson/bdb.log); "
                "refusing to treat stale logs as current run evidence"
            )
        return result

    return _set_mode_result(resolved_mode, dry_run=dry_run, apply_fn=_do_apply)


@mcp.tool()
def run_bbdev_yosys_opensta(
    top: str = "",
    config: str = "",
    mode: str = "dry-run",
    use_nix: bool = True,
    timeout_sec: int = 3600,
    quiescence_path: str = "bbdev/api/steps/yosys/log",
    quiescence_max_wait_sec: int = 600,
    quiescence_stable_window_sec: int = 30,
    quiescence_sample_sec: int = 5,
) -> str:
    """Run bbdev yosys --synth (Yosys synthesis + OpenSTA timing) in dry-run/apply modes."""
    resolved_mode = _resolve_mode(mode)
    top = top.strip()
    config = config.strip()

    args: List[str] = ["yosys", "--synth"]
    if top:
        args.append(f"--top {top}")
    if config:
        args.append(f"--config {config}")

    cmd = _bbdev_command(args, use_nix=use_nix)
    q_path = Path(quiescence_path)
    report_dir = REPO_ROOT / "bbdev" / "api" / "steps" / "yosys" / "log"
    hierarchy_path = report_dir / "hierarchy_report.txt"
    area_path = report_dir / "area_report.txt"
    timing_path = report_dir / "timing_report.txt"

    dry_run = {
        "command": " ".join(cmd),
        "timeout_sec": timeout_sec,
        "notes": "Run Yosys synthesis + OpenSTA timing analysis via bbdev.",
        "reports": {
            "hierarchy_report": str(hierarchy_path.relative_to(REPO_ROOT)),
            "area_report": str(area_path.relative_to(REPO_ROOT)),
            "timing_report": str(timing_path.relative_to(REPO_ROOT)),
        },
        "quiescence": {
            "path": str(q_path),
            "max_wait_sec": quiescence_max_wait_sec,
            "stable_window_sec": quiescence_stable_window_sec,
            "sample_sec": quiescence_sample_sec,
        },
    }

    def _do_apply() -> Dict[str, Any]:
        warmup_result = _ensure_nix_develop_initialized(
            timeout_sec=min(timeout_sec, 1200)
        )
        if use_nix and not warmup_result.get("ok"):
            return {
                "ok": False,
                "reason": "Failed to initialize nix develop environment",
                "warmup": warmup_result,
            }

        executable = cmd[0]
        if shutil.which(executable) is None:
            return {
                "ok": False,
                "reason": f"Command not found: {executable}",
                "hint": "Enable environment where bbdev is available, or set use_nix=true.",
                "warmup": warmup_result,
            }

        result = _run_command(cmd, timeout_sec=timeout_sec)
        result["warmup"] = warmup_result
        if result.get("ok"):
            result["quiescence"] = _wait_for_quiescence(
                REPO_ROOT / q_path,
                max_wait_sec=quiescence_max_wait_sec,
                stable_window_sec=quiescence_stable_window_sec,
                sample_sec=quiescence_sample_sec,
            )

        result["reports"] = {
            "hierarchy_report": {
                "path": str(hierarchy_path.relative_to(REPO_ROOT)),
                "exists": hierarchy_path.exists(),
            },
            "area_report": {
                "path": str(area_path.relative_to(REPO_ROOT)),
                "exists": area_path.exists(),
            },
            "timing_report": {
                "path": str(timing_path.relative_to(REPO_ROOT)),
                "exists": timing_path.exists(),
            },
        }
        return result

    return _set_mode_result(resolved_mode, dry_run=dry_run, apply_fn=_do_apply)


@mcp.tool()
def bbdev_yosys_synth(
    top: str = "",
    config: str = "",
    mode: str = "dry-run",
    use_nix: bool = True,
    timeout_sec: int = 3600,
    quiescence_path: str = "bbdev/api/steps/yosys/log",
    quiescence_max_wait_sec: int = 600,
    quiescence_stable_window_sec: int = 30,
    quiescence_sample_sec: int = 5,
) -> str:
    """Compatibility alias for .claude optimize flow: run Yosys synthesis + OpenSTA timing."""
    return run_bbdev_yosys_opensta(
        top=top,
        config=config,
        mode=mode,
        use_nix=use_nix,
        timeout_sec=timeout_sec,
        quiescence_path=quiescence_path,
        quiescence_max_wait_sec=quiescence_max_wait_sec,
        quiescence_stable_window_sec=quiescence_stable_window_sec,
        quiescence_sample_sec=quiescence_sample_sec,
    )


@mcp.tool()
def summarize_yosys_opensta_reports(
    module_filter: str = "",
    hierarchy_report: str = "bbdev/api/steps/yosys/log/hierarchy_report.txt",
    timing_report: str = "bbdev/api/steps/yosys/log/timing_report.txt",
    tail_lines: int = 120,
) -> str:
    """Summarize Yosys hierarchy and OpenSTA timing reports for debug/optimization handoff."""
    tail_lines = max(20, tail_lines)
    module_token = module_filter.strip().lower()
    hierarchy_path = _repo_path_from_param(hierarchy_report)
    timing_path = _repo_path_from_param(timing_report)

    if not hierarchy_path.exists():
        raise ValueError(f"hierarchy report not found: {hierarchy_path}")
    if not timing_path.exists():
        raise ValueError(f"timing report not found: {timing_path}")

    hierarchy_lines = hierarchy_path.read_text(
        encoding="utf-8", errors="replace"
    ).splitlines()
    timing_lines = timing_path.read_text(
        encoding="utf-8", errors="replace"
    ).splitlines()

    hierarchy_hits: List[str] = []
    chip_area_lines: List[str] = []
    for line in hierarchy_lines:
        stripped = line.strip()
        if "Chip area for module" in line:
            chip_area_lines.append(stripped)
        if module_token and module_token in line.lower():
            hierarchy_hits.append(stripped)

    startpoint = ""
    endpoint = ""
    path_delay = ""
    slack = ""
    timing_hits: List[str] = []
    for line in timing_lines:
        stripped = line.strip()
        if stripped.startswith("Startpoint:") and not startpoint:
            startpoint = stripped
        elif stripped.startswith("Endpoint:") and not endpoint:
            endpoint = stripped
        elif "Path Delay" in stripped and not path_delay:
            path_delay = stripped
        elif stripped.startswith("Slack") and not slack:
            slack = stripped
        if module_token and module_token in line.lower():
            timing_hits.append(stripped)

    return _ok(
        {
            "reports": {
                "hierarchy_report": str(hierarchy_path.relative_to(REPO_ROOT)),
                "timing_report": str(timing_path.relative_to(REPO_ROOT)),
            },
            "module_filter": module_filter if module_filter else None,
            "area_summary": {
                "chip_area_lines": chip_area_lines[:20],
                "module_hits": hierarchy_hits[:40],
            },
            "timing_summary": {
                "startpoint": startpoint or None,
                "endpoint": endpoint or None,
                "path_delay": path_delay or None,
                "slack": slack or None,
                "module_hits": timing_hits[:40],
            },
            "tail": {
                "hierarchy": hierarchy_lines[-tail_lines:],
                "timing": timing_lines[-tail_lines:],
            },
        }
    )


@mcp.tool()
def find_latest_bdb_log(filter_token: str = "") -> str:
    """Find latest arch/log/*/bdb.ndjson (fallback: bdb.log) with optional directory-name filter."""
    token = filter_token.strip() or None
    candidates = _candidate_log_dirs(token)
    if not candidates:
        return _ok(
            {
                "found": False,
                "arch_log_dir": str(ARCH_LOG_DIR.relative_to(REPO_ROOT)),
                "filter_token": token,
                "latest_bdb_log": None,
                "latest_bdb_artifact": None,
                "candidates": [],
            }
        )

    latest = _resolve_bdb_artifact_in_dir(candidates[0])
    candidate_paths: List[str] = []
    for d in candidates[:10]:
        artifact = _resolve_bdb_artifact_in_dir(d)
        if artifact is not None:
            candidate_paths.append(str(artifact.relative_to(REPO_ROOT)))

    return _ok(
        {
            "found": True,
            "arch_log_dir": str(ARCH_LOG_DIR.relative_to(REPO_ROOT)),
            "filter_token": token,
            "latest_bdb_log": str(latest.relative_to(REPO_ROOT)) if latest else None,
            "latest_bdb_artifact": (
                str(latest.relative_to(REPO_ROOT)) if latest else None
            ),
            "candidates": candidate_paths,
        }
    )


@mcp.tool()
def summarize_bdb_log(
    log_path: str = "",
    filter_token: str = "",
    tail_lines: int = 200,
) -> str:
    """Summarize bdb.ndjson (fallback: bdb.log) with pass/fail conclusion and ROB/memory activity counts."""
    tail_lines = max(20, tail_lines)
    log_path_str = log_path.strip()
    token = filter_token.strip() or None

    if log_path_str:
        resolved_log = (REPO_ROOT / log_path_str).resolve()
    else:
        latest = _latest_bdb_log(token)
        if latest is None:
            raise ValueError(
                "No bdb artifact found (bdb.ndjson/bdb.log). Run test first or provide log_path."
            )
        resolved_log = latest

    try:
        resolved_log.relative_to(REPO_ROOT)
    except Exception:
        raise ValueError("log_path must be inside repository.")

    if not resolved_log.exists():
        raise ValueError(f"Log file not found: {resolved_log}")

    issue_count = 0
    complete_count = 0
    read_count = 0
    write_count = 0
    pass_hits = 0
    fail_hits = 0
    pass_evidence = ""
    fail_evidence = ""
    tail: deque[str] = deque(maxlen=tail_lines)

    pass_pat = re.compile(r"\b(PASS|PASSED|SUCCESS)\b", re.IGNORECASE)
    fail_pat = re.compile(
        r"\b(FAIL|FAILED|ERROR|ASSERT|TIMEOUT|DEADLOCK)\b", re.IGNORECASE
    )

    parse_mode = "ndjson" if resolved_log.name.endswith(".ndjson") else "text"
    invalid_json_lines = 0

    with resolved_log.open("r", encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            line = raw.rstrip("\n")
            tail.append(line)

            if parse_mode == "ndjson":
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    invalid_json_lines += 1
                    obj = None

                if isinstance(obj, dict):
                    typ = str(obj.get("type", "")).lower()
                    event = str(obj.get("event", "")).lower()
                    if typ == "itrace" and event == "issue":
                        issue_count += 1
                    elif typ == "itrace" and event == "complete":
                        complete_count += 1
                    elif typ == "mtrace" and event == "read":
                        read_count += 1
                    elif typ == "mtrace" and event == "write":
                        write_count += 1
            else:
                if "[ITRACE]" in line and "ISSUE" in line:
                    issue_count += 1
                if "[ITRACE]" in line and "COMPLETE" in line:
                    complete_count += 1
                if "[MTRACE]" in line and "READ" in line:
                    read_count += 1
                if "[MTRACE]" in line and "WRITE" in line:
                    write_count += 1

            if pass_pat.search(line):
                pass_hits += 1
                if not pass_evidence:
                    pass_evidence = line[:500]
            if fail_pat.search(line):
                fail_hits += 1
                if not fail_evidence:
                    fail_evidence = line[:500]

    if fail_hits > 0:
        conclusion = "fail"
        passed = False
        evidence = fail_evidence
    elif pass_hits > 0:
        conclusion = "pass"
        passed = True
        evidence = pass_evidence
    elif complete_count > 0 and (read_count + write_count) > 0:
        conclusion = "pass_heuristic"
        passed = True
        evidence = (
            "No explicit PASS token; inferred from active ROB complete "
            "+ memory traffic without FAIL markers."
        )
    else:
        conclusion = "unknown"
        passed = False
        evidence = "No explicit PASS/FAIL token and insufficient activity evidence."

    return _ok(
        {
            "log_path": str(resolved_log.relative_to(REPO_ROOT)),
            "passed": passed,
            "conclusion": conclusion,
            "evidence": evidence,
            "counts": {
                "itrace_issue": issue_count,
                "itrace_complete": complete_count,
                "mtrace_read": read_count,
                "mtrace_write": write_count,
                "pass_hits": pass_hits,
                "fail_hits": fail_hits,
                "invalid_json_lines": invalid_json_lines,
            },
            "parse_mode": parse_mode,
            "tail": list(tail),
        }
    )


# ===================================================================== #
#                         Entry point                                     #
# ===================================================================== #


def main() -> None:
    """Start the Buckyball MCP server over stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
