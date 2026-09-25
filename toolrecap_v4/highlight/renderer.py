"""Direct original-audio Highlight renderer."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import shutil
import tempfile
from typing import Callable, Mapping

from toolrecap_v4.cancellation import CancellationToken
from toolrecap_v4.media import (
    CommandResult, EncoderStatus, find_binary, get_video_encode_args,
    nvidia_decode_args, run_command,
)
from toolrecap_v4.settings import AppSettings
from .models import HighlightOutput
from .subtitles import highlight_srt
from toolrecap_v4.original_dialogue import ORIGINAL_DIALOGUE_MAPPED, NO_ORIGINAL_DIALOGUE


@dataclass(frozen=True)
class HighlightRenderResult:
    output_id: str
    video_path: Path
    subtitle_path: Path
    video_sha256: str
    subtitle_sha256: str
    original_subtitle_state: str = NO_ORIGINAL_DIALOGUE
    original_subtitle_cue_count: int = 0


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def render_highlight(
    output: HighlightOutput, *, sources: Mapping[str, Path | str], publication_dir: Path | str,
    ffmpeg_path: Path | str | None = None,
    settings: AppSettings | None = None,
    encoder_status: EncoderStatus | None = None,
    source_codec: str = "h264",
    source_pixel_format: str = "",
    command_runner: Callable[..., CommandResult] = run_command,
    cancellation_token: CancellationToken | None = None,
) -> HighlightRenderResult:
    """Publish exactly one MP4 and one relative-timestamp SRT.

    No narration, VoiceStudio, Narration Fit, tempo adjustment, or synthetic
    audio enters this path.  Video and original source audio are trimmed from
    one episode sequence at normal playback rate.
    """
    if not output.original_audio:
        raise ValueError("Highlight outputs must preserve original source audio")
    if output.source_file not in sources:
        raise ValueError(f"Missing Highlight source: {output.source_file}")
    source = Path(sources[output.source_file]).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    target_dir = Path(publication_dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    video = target_dir / f"{output.title}.mp4"
    subtitle = target_dir / f"{output.title}.srt"
    if source in (video.resolve(), subtitle.resolve()):
        raise ValueError("Highlight publication collides with its source")
    ffmpeg = find_binary("ffmpeg", ffmpeg_path)
    cfg = settings or AppSettings()
    video_args, selected_encoder = get_video_encode_args(
        cfg.quality, use_gpu=cfg.use_gpu, encoder_status=encoder_status, ffmpeg_path=ffmpeg,
    )
    if cancellation_token:
        cancellation_token.check_cancelled()
    with tempfile.TemporaryDirectory(prefix="toolrecap_highlight_", dir=target_dir) as temp_name:
        temp = Path(temp_name)
        staged_video = temp / "highlight.mp4"
        staged_srt = temp / "highlight.srt"
        duration = (output.end_ms - output.start_ms) / 1000.0
        decode_args = nvidia_decode_args(source_codec, selected_encoder, source_pixel_format)
        nvenc_format_args = (
            ["-vf", "scale_cuda=format=nv12"]
            if selected_encoder.encoder == "h264_nvenc" and decode_args
            else []
        )
        args = [
            str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y",
            "-accurate_seek", "-ss", f"{output.start_ms / 1000.0:.3f}",
            *decode_args, "-i", str(source),
            "-t", f"{duration:.3f}", "-map", "0:v:0", "-map", "0:a?",
            *nvenc_format_args,
            *video_args,
            "-c:a", "aac", "-b:a", "192k", "-avoid_negative_ts", "make_zero",
            str(staged_video),
        ]
        try:
            result = command_runner(args, timeout=max(120.0, duration * 4.0), cancellation_token=cancellation_token)
        except Exception as exc:
            if selected_encoder.encoder == "h264_nvenc":
                raise RuntimeError(f"NVIDIA GPU render unavailable: NVENC initialization failed: {exc}") from exc
            raise
        if result.exit_code != 0 or not staged_video.is_file():
            prefix = "NVIDIA GPU render unavailable: NVENC initialization failed" if selected_encoder.encoder == "h264_nvenc" else "Highlight render failed"
            raise RuntimeError(f"{prefix}: {result.stderr[-3000:]}")
        staged_srt.write_text(highlight_srt(output), encoding="utf-8", newline="\n")
        if cancellation_token:
            cancellation_token.check_cancelled()
        os.replace(staged_video, video)
        os.replace(staged_srt, subtitle)
    cue_count = len(output.subtitle_cues)
    return HighlightRenderResult(
        output.output_id, video, subtitle, _sha(video), _sha(subtitle),
        ORIGINAL_DIALOGUE_MAPPED if cue_count else NO_ORIGINAL_DIALOGUE, cue_count,
    )
