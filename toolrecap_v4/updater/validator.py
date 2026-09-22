"""Validation of extracted update package contents."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from toolrecap_v4.errors import PackageValidationError

EXPECTED_SCHEMA_VERSION = "3.0"


def find_executable(package_dir: Path, names: list[str]) -> Optional[Path]:
    """Search for executable matching any of the candidate names."""
    for name in names:
        # Check root
        candidate = package_dir / name
        if candidate.is_file():
            return candidate
        # Check bin/
        candidate_bin = package_dir / "bin" / name
        if candidate_bin.is_file():
            return candidate_bin
    return None


def validate_package(
    package_dir: Path,
    expected_version: Optional[str] = None,
) -> None:
    """Validate that extracted package contains all required components.
    
    Required:
    - Main executable: ToolRecapV4.exe (or toolrecap_v4.exe)
    - Media binaries: ffmpeg.exe and ffprobe.exe (root or bin/)
    - Package marker / schema version: package_marker.json, version.json, or schemas/recap_v3_schema.json
      with valid schema_version == "3.0" and matching version.
    
    Raises:
        PackageValidationError: If any required component is missing or invalid.
    """
    package_dir = Path(package_dir).resolve()
    if not package_dir.is_dir():
        raise PackageValidationError(f"Package path is not a directory: {package_dir}")

    # 1. Check main executable
    exe = find_executable(package_dir, ["ToolRecapV4.exe", "toolrecapv4.exe", "toolrecap_v4.exe", "ToolRecapV4"])
    if not exe:
        raise PackageValidationError("Package is missing main executable 'ToolRecapV4.exe'")

    # 2. Check ffmpeg
    ffmpeg = find_executable(package_dir, ["ffmpeg.exe", "ffmpeg"])
    if not ffmpeg:
        raise PackageValidationError("Package is missing 'ffmpeg.exe'")

    # 3. Check ffprobe
    ffprobe = find_executable(package_dir, ["ffprobe.exe", "ffprobe"])
    if not ffprobe:
        raise PackageValidationError("Package is missing 'ffprobe.exe'")

    # 4. Check schema version / package marker
    marker_candidates = [
        package_dir / "package_marker.json",
        package_dir / "package.json",
        package_dir / "version.json",
        package_dir / "schemas" / "recap_v3_schema.json",
        package_dir / "toolrecap_v4" / "schemas" / "recap_v3_schema.json",
    ]

    found_marker = False
    for marker_path in marker_candidates:
        if marker_path.is_file():
            try:
                with open(marker_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                raise PackageValidationError(f"Invalid JSON in package marker {marker_path.name}: {e}") from e

            # Case A: package_marker / version.json with top-level schema_version
            if "schema_version" in data:
                schema_ver = str(data["schema_version"]).strip()
                if schema_ver != EXPECTED_SCHEMA_VERSION:
                    raise PackageValidationError(
                        f"Package schema_version '{schema_ver}' does not match expected '{EXPECTED_SCHEMA_VERSION}'"
                    )
                if expected_version and "version" in data:
                    pkg_ver = str(data["version"]).strip().lstrip("vV")
                    clean_expected = expected_version.strip().lstrip("vV")
                    if pkg_ver != clean_expected:
                        raise PackageValidationError(
                            f"Package version '{pkg_ver}' does not match expected '{clean_expected}'"
                        )
                found_marker = True
                break

            # Case B: schema definition file (e.g. recap_v3_schema.json)
            if "properties" in data and "schema_version" in data["properties"]:
                prop = data["properties"]["schema_version"]
                const_val = prop.get("const") or (prop.get("enum", [None])[0] if "enum" in prop else None)
                if str(const_val) != EXPECTED_SCHEMA_VERSION:
                    raise PackageValidationError(
                        f"Schema definition version '{const_val}' does not match expected '{EXPECTED_SCHEMA_VERSION}'"
                    )
                found_marker = True
                break

    if not found_marker:
        raise PackageValidationError(
            "Package is missing schema version or package marker (package_marker.json or recap_v3_schema.json)"
        )
