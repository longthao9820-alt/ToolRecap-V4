"""Reusable repackaging script to refresh bundled docs, validate package, and re-zip existing dist."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

from toolrecap_v4.__version__ import __version__
from toolrecap_v4.updater.archive import parse_sha256_content, verify_checksum
from toolrecap_v4.updater.validator import validate_package

PROJECT_ROOT = Path(__file__).resolve().parent
DIST_DIR = PROJECT_ROOT / "dist" / "ToolRecapV4"
RELEASE_DIR = PROJECT_ROOT / "release"
RELEASE_ZIP = RELEASE_DIR / f"ToolRecapV4-v{__version__}-windows-portable.zip"
RELEASE_SHA = RELEASE_DIR / f"{RELEASE_ZIP.name}.sha256.txt"


def calculate_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest().lower()


def repackage() -> str:
    print(f"Refreshing bundled docs and repackaging {DIST_DIR} (v{__version__})...")

    # 1. Refresh documentation copies in dist and release
    for doc_name in ("README.md", "IMPLEMENTATION_REPORT.md", "PHASE1_REPORT.md"):
        doc_src = PROJECT_ROOT / doc_name
        assert doc_src.is_file(), f"Missing source documentation: {doc_src}"
        shutil.copy2(doc_src, DIST_DIR / doc_name)
        shutil.copy2(doc_src, RELEASE_DIR / doc_name)
        print(f"Refreshed {doc_name} in dist and release")

    # 2. Validate dist package directory structure
    print("Validating package directory...")
    validate_package(DIST_DIR, expected_version=__version__)
    print("Package directory validation PASSED")

    # 3. Create portable ZIP archive
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)
    if RELEASE_ZIP.exists():
        RELEASE_ZIP.unlink()
    if RELEASE_SHA.exists():
        RELEASE_SHA.unlink()

    print(f"Creating portable zip: {RELEASE_ZIP}...")
    with zipfile.ZipFile(RELEASE_ZIP, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for file_path in DIST_DIR.rglob("*"):
            if file_path.is_file():
                arcname = file_path.relative_to(DIST_DIR)
                zf.write(file_path, arcname)

    assert RELEASE_ZIP.is_file(), f"Zip file not created: {RELEASE_ZIP}"
    zip_size_mb = RELEASE_ZIP.stat().st_size / (1024 * 1024)
    print(f"Created portable zip: {RELEASE_ZIP} ({zip_size_mb:.2f} MB)")

    # 4. Compute and write checksum
    sha256 = calculate_sha256(RELEASE_ZIP)
    sha_content = f"{sha256}  {RELEASE_ZIP.name}\n"
    RELEASE_SHA.write_text(sha_content, encoding="utf-8")
    print(f"Checksum SHA256: {sha256}")

    # 5. Verify checksum
    parsed_sha = parse_sha256_content(RELEASE_SHA.read_text(encoding="utf-8"))
    assert parsed_sha == sha256, f"Parsed sha mismatch: {parsed_sha} != {sha256}"
    assert verify_checksum(RELEASE_ZIP, sha256), "verify_checksum failed"
    print("Checksum verification PASSED")

    # 6. Verify dist executable with --selfcheck on clean PATH
    print("Testing dist executable with --selfcheck on clean PATH...")
    clean_env = {
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", r"C:\Windows"),
        "PATH": r"C:\Windows\System32;C:\Windows",
        "TMP": tempfile.gettempdir(),
        "TEMP": tempfile.gettempdir(),
    }
    exe_path = DIST_DIR / "ToolRecapV4.exe"
    assert exe_path.is_file(), f"Executable not found: {exe_path}"

    test_report_file = PROJECT_ROOT / "dist" / "selfcheck_test_report.json"
    if test_report_file.exists():
        test_report_file.unlink()

    proc = subprocess.run(
        [str(exe_path), "--selfcheck", "--selfcheck-json", str(test_report_file)],
        env=clean_env,
        cwd=str(DIST_DIR),
        capture_output=True,
        text=True,
        timeout=60,
    )
    if proc.returncode != 0:
        print(f"Selfcheck stderr: {proc.stderr}")
        print(f"Selfcheck stdout: {proc.stdout}")
        raise RuntimeError(f"Selfcheck failed with exit code {proc.returncode}")

    assert test_report_file.is_file(), f"Report file {test_report_file} not written"
    report = json.loads(test_report_file.read_text(encoding="utf-8"))
    assert report.get("status") == "ok", f"Selfcheck non-ok: {report}"
    assert report.get("checks", {}).get("version", {}).get("version") == __version__
    assert report.get("checks", {}).get("schema", {}).get("schema_version") == "3.0"
    assert report.get("checks", {}).get("ffmpeg", {}).get("status") == "ok"
    assert report.get("checks", {}).get("ffprobe", {}).get("status") == "ok"
    test_report_file.unlink()
    print("Selfcheck PASSED")

    return sha256


if __name__ == "__main__":
    final_sha = repackage()
    print(f"FINAL_SHA: {final_sha}")
