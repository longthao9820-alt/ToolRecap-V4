"""Build and package ToolRecap V4 portable Windows distribution."""

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

PROJECT_ROOT = Path(__file__).resolve().parent
DIST_DIR = PROJECT_ROOT / "dist" / "ToolRecapV4"
RELEASE_DIR = PROJECT_ROOT / "release"
RELEASE_ZIP = RELEASE_DIR / f"ToolRecapV4-v{__version__}-windows-portable.zip"
RELEASE_SHA = RELEASE_DIR / f"{RELEASE_ZIP.name}.sha256.txt"

FFMPEG_SRC = Path(os.environ["TOOLRECAP_FFMPEG_DISTRIBUTION"]) if os.environ.get("TOOLRECAP_FFMPEG_DISTRIBUTION") else Path(shutil.which("ffmpeg") or "ffmpeg.exe").resolve().parent.parent


def calculate_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest().lower()


def build() -> None:
    print("[1/6] Verifying environment and dependencies...")
    assert sys.version_info >= (3, 12), f"Requires Python 3.12+, got {sys.version}"

    ffmpeg_bin = FFMPEG_SRC / "bin" / "ffmpeg.exe"
    ffprobe_bin = FFMPEG_SRC / "bin" / "ffprobe.exe"
    ffmpeg_license = FFMPEG_SRC / "LICENSE"
    schema_src = PROJECT_ROOT / "toolrecap_v4" / "schemas" / "recap_v3_schema.json"

    assert ffmpeg_bin.is_file(), f"Missing {ffmpeg_bin}"
    assert ffprobe_bin.is_file(), f"Missing {ffprobe_bin}"
    assert ffmpeg_license.is_file(), f"Missing {ffmpeg_license}"
    assert schema_src.is_file(), f"Missing {schema_src}"

    # Clean previous build artifacts
    build_work_dir = PROJECT_ROOT / "build" / "ToolRecapV4"
    if DIST_DIR.exists():
        print(f"Cleaning existing dist directory: {DIST_DIR}")
        shutil.rmtree(DIST_DIR, ignore_errors=True)
    if build_work_dir.exists():
        shutil.rmtree(build_work_dir, ignore_errors=True)

    RELEASE_DIR.mkdir(parents=True, exist_ok=True)

    print("[2/6] Running PyInstaller 6.22.2...")
    pyinstaller_cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onedir",
        "--windowed",
        "--name=ToolRecapV4",
        "--noconfirm",
        "--clean",
        f"--add-data={schema_src};toolrecap_v4/schemas",
        f"--add-data={schema_src};schemas",
        "--collect-all=windows_toasts",
        "--collect-all=winrt",
        "--hidden-import=tkinter",
        "--hidden-import=toolrecap_v4",
        "--hidden-import=toolrecap_v4.selfcheck",
        "--hidden-import=toolrecap_v4.updater.helper",
        "--hidden-import=toolrecap_v4.updater.validator",
        "--hidden-import=toolrecap_v4.updater.archive",
        "--hidden-import=toolrecap_v4.updater.manager",
        "--hidden-import=toolrecap_v4.schemas.schema",
        str(PROJECT_ROOT / "main.py"),
    ]

    res = subprocess.run(pyinstaller_cmd, cwd=PROJECT_ROOT, check=False)
    if res.returncode != 0:
        raise RuntimeError(f"PyInstaller failed with exit code {res.returncode}")

    assert DIST_DIR.is_dir(), f"Dist directory {DIST_DIR} was not created"
    exe_path = DIST_DIR / "ToolRecapV4.exe"
    assert exe_path.is_file(), f"Main executable {exe_path} not found"

    print("[3/6] Bundling FFmpeg, license, schemas, and package_marker...")
    # Copy FFmpeg binaries to root and bin/
    shutil.copy2(ffmpeg_bin, DIST_DIR / "ffmpeg.exe")
    shutil.copy2(ffprobe_bin, DIST_DIR / "ffprobe.exe")

    bin_dir = DIST_DIR / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ffmpeg_bin, bin_dir / "ffmpeg.exe")
    shutil.copy2(ffprobe_bin, bin_dir / "ffprobe.exe")

    # Copy FFmpeg LICENSE
    shutil.copy2(ffmpeg_license, DIST_DIR / "LICENSE")

    # Copy documentation (README and Implementation Report)
    for doc_name in ("README.md", "IMPLEMENTATION_REPORT.md", "PHASE1_REPORT.md"):
        doc_src = PROJECT_ROOT / doc_name
        if doc_src.is_file():
            shutil.copy2(doc_src, DIST_DIR / doc_name)
            shutil.copy2(doc_src, RELEASE_DIR / doc_name)
            print(f"Bundled {doc_name} into dist and release")

    # Copy schema definition
    schemas_dst = DIST_DIR / "schemas"
    schemas_dst.mkdir(parents=True, exist_ok=True)
    shutil.copy2(schema_src, schemas_dst / "recap_v3_schema.json")

    # Create package marker
    marker_content = {
        "schema_version": "3.0",
        "version": __version__,
    }
    marker_path = DIST_DIR / "package_marker.json"
    marker_path.write_text(json.dumps(marker_content, indent=2), encoding="utf-8")

    print("[4/6] Validating package directory structure...")
    from toolrecap_v4.updater.validator import validate_package

    validate_package(DIST_DIR, expected_version=__version__)
    print("Package directory validation PASSED")

    print("[5/6] Creating portable ZIP archive and SHA256 checksum...")
    if RELEASE_ZIP.exists():
        RELEASE_ZIP.unlink()
    if RELEASE_SHA.exists():
        RELEASE_SHA.unlink()

    with zipfile.ZipFile(RELEASE_ZIP, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for file_path in DIST_DIR.rglob("*"):
            if file_path.is_file():
                arcname = file_path.relative_to(DIST_DIR)
                zf.write(file_path, arcname)

    assert RELEASE_ZIP.is_file(), f"Zip file not created: {RELEASE_ZIP}"
    zip_size_mb = RELEASE_ZIP.stat().st_size / (1024 * 1024)
    print(f"Created portable zip: {RELEASE_ZIP} ({zip_size_mb:.2f} MB)")

    # Compute checksum
    sha256 = calculate_sha256(RELEASE_ZIP)
    sha_content = f"{sha256}  {RELEASE_ZIP.name}\n"
    RELEASE_SHA.write_text(sha_content, encoding="utf-8")
    print(f"Checksum SHA256: {sha256}")

    # Verify checksum using updater archive verifier
    from toolrecap_v4.updater.archive import parse_sha256_content, verify_checksum

    parsed_sha = parse_sha256_content(RELEASE_SHA.read_text(encoding="utf-8"))
    assert parsed_sha == sha256, f"Parsed sha mismatch: {parsed_sha} != {sha256}"
    assert verify_checksum(RELEASE_ZIP, sha256), "verify_checksum failed"
    print("Checksum verification PASSED")

    print("[6/6] Testing built executable with --selfcheck on clean PATH...")
    # Clean PATH: ONLY C:\Windows\System32 and C:\Windows
    # No Python in PATH, no system FFmpeg in PATH
    clean_env = {
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", r"C:\Windows"),
        "PATH": r"C:\Windows\System32;C:\Windows",
        "TMP": tempfile.gettempdir(),
        "TEMP": tempfile.gettempdir(),
    }

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
        raise RuntimeError(f"Standalone executable --selfcheck failed with exit code {proc.returncode}")

    assert test_report_file.is_file(), f"Report file {test_report_file} was not written"
    report = json.loads(test_report_file.read_text(encoding="utf-8"))
    print("Selfcheck report outcome:")
    print(json.dumps(report, indent=2))
    assert report.get("status") == "ok", f"Selfcheck reported non-ok status: {report}"
    assert report.get("checks", {}).get("version", {}).get("version") == __version__
    assert report.get("checks", {}).get("schema", {}).get("schema_version") == "3.0"
    assert report.get("checks", {}).get("ffmpeg", {}).get("status") == "ok"
    assert report.get("checks", {}).get("ffprobe", {}).get("status") == "ok"
    test_report_file.unlink()

    # Also test extracting the zip and validating
    print("Verifying zip archive extraction and validation...")
    with tempfile.TemporaryDirectory() as tmp_extract:
        tmp_extract_path = Path(tmp_extract)
        from toolrecap_v4.updater.archive import safe_extract_zip

        safe_extract_zip(RELEASE_ZIP, tmp_extract_path)
        validate_package(tmp_extract_path, expected_version=__version__)

        # Test running selfcheck from extracted zip
        extracted_exe = tmp_extract_path / "ToolRecapV4.exe"
        extracted_report = tmp_extract_path / "extracted_selfcheck.json"
        res_ext = subprocess.run(
            [str(extracted_exe), "--selfcheck", "--selfcheck-json", str(extracted_report)],
            env=clean_env,
            cwd=str(tmp_extract_path),
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert res_ext.returncode == 0, f"Extracted EXE selfcheck failed: {res_ext.stderr}"
        assert extracted_report.is_file(), "Extracted report file not found"
        ext_rep_data = json.loads(extracted_report.read_text(encoding="utf-8"))
        assert ext_rep_data.get("status") == "ok"

    print("ALL PACKAGING AND ACCEPTANCE CHECKS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    build()
