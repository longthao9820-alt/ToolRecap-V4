"""Settings configuration and defaults for ToolRecap V4.

Defaults match the specified requirements:
- Audio: original 0.0 dB, commentary 0.0 dB, duck OFF, ducking amount -12.0 dB,
  target loudness -14.0 LUFS, true peak -1.0 dBTP.
- GPU: True (GPU on).
- Voice: alloy, language en-US, style configurable.
- VoiceStudio: mode auto, local http://127.0.0.1:3900, remote https://desktop-t5c9b90.tail7b66e0.ts.net:8443.
- AI Gateway: endpoint http://127.0.0.1:20128, model ag/gemini-3.8-flash.
- Notifications: all defaults ON.
- Secrets: strictly separated; never stored in settings JSON.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from toolrecap_v4.persistence import ProjectPersistence, get_storage_root


@dataclass
class AppSettings:
    # Audio mix
    original_audio_db: float = 0.0
    commentary_audio_db: float = 0.0
    auto_duck: bool = False
    ducking_amount_db: float = -12.0
    target_loudness_lufs: float = -14.0
    true_peak_db: float = -1.0

    # Hardware & render
    use_gpu: bool = True
    quality: str = "high"
    video_codec: str = "h264"
    canvas_width: int = 1920
    canvas_height: int = 1080
    canvas_fps: float = 30.0
    canvas_auto: bool = True
    burn_subtitles: bool = False
    output_format: str = "mp4"
    output_dir: str = ""

    # Voice & VoiceStudio
    voice_mode: str = "auto"  # "auto", "local", "remote"
    voice_local_url: str = "http://127.0.0.1:3900"
    voice_remote_url: str = ""
    voice_id: str = "alloy"
    voice_language: str = "en-US"
    voice_style: str = ""
    voice_model: str = "omnivoice"

    # AI Gateway (Dual-Stage: Sub for video analysis, Prime for synthesis)
    gateway_endpoint: str = "http://127.0.0.1:20128"
    gateway_sub_model: str = "sub"
    gateway_sub_reasoning: str = ""
    gateway_prime_model: str = "prime"
    gateway_prime_reasoning: str = ""
    gateway_model: str = "sub"
    gateway_thinking: bool = False

    # Phase 4 factual Scanner. Empty on a fresh install until explicitly configured.
    # Existing V3/V4 settings are migrated from gateway_sub_* by from_dict().
    scanner_model: str = ""
    scanner_reasoning: str = ""
    scanner_parallelism: int = 3
    scanner_chunk_duration_ms: int = 300_000
    scanner_max_request_bytes: int = 131_072
    scanner_repair_attempts: int = 1

    # Notifications (all defaults ON)
    notify_complete: bool = True
    notify_error: bool = True
    play_completion_sound: bool = True
    flash_taskbar: bool = True
    notify_update: bool = True

    # Updater
    update_repo: str = "longthao9820-alt/ToolRecap-V4"

    # Prompt
    prompt: str = ""

    # Recap metadata (V2 compatible)
    recap_language: str = "en-US"
    recap_mode: str = "MAIN_STORIES"
    content_type: str = "US_TV_SHOW"
    source_rights_status: str = "UNVERIFIED"

    def __post_init__(self) -> None:
        if self.canvas_auto is None:
            self.canvas_auto = True
        if self.gateway_sub_model and (not self.gateway_model or self.gateway_model == "sub"):
            self.gateway_model = self.gateway_sub_model
        elif self.gateway_model and not self.gateway_sub_model:
            self.gateway_sub_model = self.gateway_model
        if self.scanner_parallelism < 1:
            raise ValueError("scanner_parallelism must be at least 1")
        if self.scanner_chunk_duration_ms < 1:
            raise ValueError("scanner_chunk_duration_ms must be positive")
        if self.scanner_max_request_bytes < 1024:
            raise ValueError("scanner_max_request_bytes must be at least 1024")
        if self.scanner_repair_attempts < 0:
            raise ValueError("scanner_repair_attempts must be non-negative")

    def to_dict(self) -> Dict[str, Any]:
        """Convert settings to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AppSettings:
        """Create AppSettings from dict, safely migrating legacy gateway_model and thinking if needed."""
        data_copy = dict(data)
        # Transitional Phase 3 names become provider-neutral Scanner configuration.
        # Preserve the literal user-selected ID; never infer a provider from it.
        if "scanner_model" not in data_copy:
            data_copy["scanner_model"] = str(data_copy.get("gateway_sub_model") or data_copy.get("gateway_model") or "")
        if "scanner_reasoning" not in data_copy:
            data_copy["scanner_reasoning"] = str(data_copy.get("gateway_sub_reasoning") or "")
        # Migrate legacy single gateway_model to dual sub/prime defaults
        if "gateway_model" in data_copy and "gateway_sub_model" not in data_copy:
            old_model = data_copy.get("gateway_model")
            if old_model:
                data_copy["gateway_sub_model"] = old_model
            if "gateway_prime_model" not in data_copy:
                data_copy["gateway_prime_model"] = "prime"
        if "gateway_sub_model" in data_copy and "gateway_model" not in data_copy:
            data_copy["gateway_model"] = data_copy["gateway_sub_model"]
        if "gateway_thinking" in data_copy:
            if "gateway_sub_reasoning" not in data_copy and data_copy["gateway_thinking"]:
                data_copy["gateway_sub_reasoning"] = "high"
            if "gateway_prime_reasoning" not in data_copy and data_copy["gateway_thinking"]:
                data_copy["gateway_prime_reasoning"] = "high"
        # Migrate old settings without canvas_auto to auto default
        if "canvas_auto" not in data_copy or data_copy.get("canvas_auto") is None:
            data_copy["canvas_auto"] = True
        allowed = cls.__dataclass_fields__
        filtered = {k: v for k, v in data_copy.items() if k in allowed}
        return cls(**filtered)


class SettingsManager:
    """Manages reading and writing application settings in LOCALAPPDATA."""

    def __init__(self, persistence: Optional[ProjectPersistence] = None, storage_root: Optional[Path | str] = None) -> None:
        if persistence is not None:
            self.persistence = persistence
        else:
            self.persistence = ProjectPersistence(storage_root=storage_root)

    def load(self) -> AppSettings:
        """Load settings from persistence; returns default AppSettings if absent or corrupted."""
        try:
            raw = self.persistence.load_settings()
            return AppSettings.from_dict(raw)
        except Exception:
            return AppSettings()

    def save(self, settings: AppSettings) -> Path:
        """Persist settings to LOCALAPPDATA atomically."""
        return self.persistence.save_settings(settings.to_dict())
