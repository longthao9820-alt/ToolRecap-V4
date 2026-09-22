"""Tests for durable atomic persistence in LOCALAPPDATA with secret prevention."""

import os
from pathlib import Path
import pytest

from toolrecap_v4.errors import PersistenceError, SecretExposureError
from toolrecap_v4.persistence import (
    DEFAULT_APP_DIR_NAME,
    ProjectPersistence,
    atomic_write_json,
    get_storage_root,
    read_json,
)


def test_storage_root_in_localappdata(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Verify default storage root is strictly located in LOCALAPPDATA, never app dir."""
    fake_local_app_data = str(tmp_path / "AppData" / "Local")
    monkeypatch.setenv("LOCALAPPDATA", fake_local_app_data)

    root = get_storage_root()

    assert str(root).startswith(fake_local_app_data)
    assert root.name == DEFAULT_APP_DIR_NAME
    assert root.exists()


def test_atomic_project_state_roundtrip(tmp_path: Path) -> None:
    """Verify atomic project save and load roundtrip reproduces exact JSON."""
    persistence = ProjectPersistence(storage_root=tmp_path)

    project_data = {
        "schema_version": "3.0",
        "project_id": "proj-roundtrip-01",
        "project_name": "Test_Project",
        "sources": [{"source_file": "ep1.mp4"}],
        "outputs": [
            {
                "render_id": "render-01",
                "title": "Recap_1",
                "segments": [
                    {
                        "segment_id": "seg-1",
                        "source_file": "ep1.mp4",
                        "start_ms": 0,
                        "end_ms": 1000,
                        "type": "narration",
                        "narration": "Text",
                        "source_audio": False,
                        "subtitles": [],
                    }
                ],
            }
        ],
    }

    saved_path = persistence.save_project(project_data)
    assert saved_path.exists()
    assert saved_path.suffix == ".json"

    loaded_data = persistence.load_project("proj-roundtrip-01")
    assert loaded_data == project_data


def test_atomic_checkpoint_roundtrip(tmp_path: Path) -> None:
    """Verify checkpoint save and load roundtrip."""
    persistence = ProjectPersistence(storage_root=tmp_path)

    checkpoint_data = {
        "checkpoint_id": "ckpt-01",
        "render_id": "render-01",
        "status": "in_progress",
        "progress_percent": 45,
    }

    saved_path = persistence.save_checkpoint("proj-01", "ckpt-01", checkpoint_data)
    assert saved_path.exists()

    loaded_data = persistence.load_checkpoint("proj-01", "ckpt-01")
    assert loaded_data == checkpoint_data


def test_atomic_settings_roundtrip(tmp_path: Path) -> None:
    """Verify settings save and load roundtrip."""
    persistence = ProjectPersistence(storage_root=tmp_path)

    settings = {
        "theme": "dark",
        "default_recap_mode": "FULL_RECAP",
    }

    saved_path = persistence.save_settings(settings)
    assert saved_path.exists()

    loaded_settings = persistence.load_settings()
    assert loaded_settings == settings


def test_atomic_write_cleans_up_temp_file(tmp_path: Path) -> None:
    """Verify atomic write leaves no temporary files behind on success."""
    target_file = tmp_path / "data.json"
    data = {"key": "value"}

    atomic_write_json(target_file, data)

    assert target_file.exists()
    tmp_files = list(tmp_path.glob("*.tmp.*"))
    assert len(tmp_files) == 0


def test_secrets_never_persisted_in_project_json(tmp_path: Path) -> None:
    """Verify any secret keys are rejected before disk write, leaving no file."""
    persistence = ProjectPersistence(storage_root=tmp_path)

    project_data = {
        "project_id": "proj-secrets",
        "project_name": "Secret_Project",
        "api_key": "sk-secret-token-12345",
    }

    with pytest.raises(SecretExposureError, match="Forbidden secret key detected"):
        persistence.save_project(project_data)

    target_file = tmp_path / "projects" / "proj-secrets.json"
    assert not target_file.exists()


def test_nested_secrets_rejected_before_persistence(tmp_path: Path) -> None:
    """Verify nested secret keys are also detected and rejected."""
    persistence = ProjectPersistence(storage_root=tmp_path)

    checkpoint_data = {
        "checkpoint_id": "ckpt-secret",
        "render_id": "render-01",
        "auth": {
            "token": "bearer-123",
        },
    }

    with pytest.raises(SecretExposureError, match="Forbidden secret key detected"):
        persistence.save_checkpoint("proj-01", "ckpt-secret", checkpoint_data)
