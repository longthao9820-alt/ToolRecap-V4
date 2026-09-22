"""Non-GUI self-check verification for frozen or installed runtime."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Dict, Optional

from toolrecap_v4.__version__ import __version__
from toolrecap_v4.media import find_binary
from toolrecap_v4.schemas.schema import get_project_schema, get_schema_validator


def _safe_write_stdout(msg: str) -> None:
    if sys.stdout is not None:
        try:
            sys.stdout.write(msg + "\n")
            sys.stdout.flush()
        except Exception:
            pass


def _safe_write_stderr(msg: str) -> None:
    if sys.stderr is not None:
        try:
            sys.stderr.write(msg + "\n")
            sys.stderr.flush()
        except Exception:
            pass


def determine_report_path(argv: Optional[list[str]] = None) -> Optional[Path]:
    """Parse report path from command line arguments."""
    args = sys.argv if argv is None else argv
    for flag in ["--selfcheck-json", "--report", "--json-report"]:
        if flag in args:
            idx = args.index(flag)
            if idx + 1 < len(args):
                return Path(args[idx + 1]).resolve()

    # Check positional argument right after --selfcheck if not a flag
    if "--selfcheck" in args:
        idx = args.index("--selfcheck")
        if idx + 1 < len(args) and not args[idx + 1].startswith("-"):
            return Path(args[idx + 1]).resolve()

    return None


def run_selfcheck(argv: Optional[list[str]] = None) -> int:
    """Execute complete selfcheck verification.
    
    Verifies:
    1. Application version
    2. JSON schema definition and validator
    3. Bundled/accessible FFmpeg executable and version
    4. Bundled/accessible FFprobe executable and version
    
    Writes a JSON report to the specified path or default locations,
    outputs to stdout if available, and returns 0 on success, non-zero on failure.
    """
    report_path = determine_report_path(argv)
    if report_path is None:
        # Default report path in current working directory
        report_path = Path.cwd() / "selfcheck_report.json"

    report_data: Dict[str, Any] = {
        "status": "in_progress",
        "app_version": __version__,
        "frozen": getattr(sys, "frozen", False),
        "checks": {},
    }

    try:
        # 1. Version check
        if not __version__ or not isinstance(__version__, str):
            raise ValueError(f"Invalid application version: {__version__}")
        report_data["checks"]["version"] = {
            "status": "ok",
            "version": __version__,
        }

        # 2. Schema check
        schema = get_project_schema()
        validator = get_schema_validator()
        if not isinstance(schema, dict) or not schema:
            raise ValueError("Project schema failed to load or is empty")
        schema_version = schema.get("properties", {}).get("schema_version", {}).get("const", "unknown")
        report_data["checks"]["schema"] = {
            "status": "ok",
            "schema_version": schema_version,
            "title": schema.get("title", ""),
        }

        # 3. FFmpeg check
        ffmpeg_path = find_binary("ffmpeg")
        if not ffmpeg_path.is_file():
            raise FileNotFoundError(f"FFmpeg binary not found at {ffmpeg_path}")

        creationflags = 0
        if sys.platform == "win32":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

        res_ffmpeg = subprocess.run(
            [str(ffmpeg_path), "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
            creationflags=creationflags,
        )
        if res_ffmpeg.returncode != 0:
            raise RuntimeError(f"FFmpeg check exited with returncode {res_ffmpeg.returncode}: {res_ffmpeg.stderr[:200]}")
        first_line_ffmpeg = res_ffmpeg.stdout.splitlines()[0] if res_ffmpeg.stdout else ""

        report_data["checks"]["ffmpeg"] = {
            "status": "ok",
            "path": str(ffmpeg_path),
            "version": first_line_ffmpeg,
        }

        # 4. FFprobe check
        ffprobe_path = find_binary("ffprobe")
        if not ffprobe_path.is_file():
            raise FileNotFoundError(f"FFprobe binary not found at {ffprobe_path}")

        res_ffprobe = subprocess.run(
            [str(ffprobe_path), "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
            creationflags=creationflags,
        )
        if res_ffprobe.returncode != 0:
            raise RuntimeError(f"FFprobe check exited with returncode {res_ffprobe.returncode}: {res_ffprobe.stderr[:200]}")
        first_line_ffprobe = res_ffprobe.stdout.splitlines()[0] if res_ffprobe.stdout else ""

        report_data["checks"]["ffprobe"] = {
            "status": "ok",
            "path": str(ffprobe_path),
            "version": first_line_ffprobe,
        }

        report_data["status"] = "ok"

        # Write report JSON
        try:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report_data, indent=2), encoding="utf-8")
        except Exception as e:
            _safe_write_stderr(f"Warning: Failed to write report file {report_path}: {e}")

        json_output = json.dumps(report_data, indent=2)
        _safe_write_stdout(json_output)
        return 0

    except Exception as exc:
        report_data["status"] = "error"
        report_data["error"] = str(exc)
        try:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report_data, indent=2), encoding="utf-8")
        except Exception:
            pass

        _safe_write_stderr(f"Selfcheck failed: {exc}")
        json_output = json.dumps(report_data, indent=2)
        _safe_write_stdout(json_output)
        return 1
