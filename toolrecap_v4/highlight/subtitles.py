"""Verified original-dialogue SRT creation for Highlight Mode."""
from __future__ import annotations

from toolrecap_v4.original_dialogue import OriginalDialogueSubtitleMapper, ResolvedSourceClip
from toolrecap_v4.subtitles import SubtitleCue, build_srt
from .models import HighlightOutput


def highlight_srt(output: HighlightOutput) -> str:
    """Map verified source-global cues through the shared authoritative mapper."""
    source_cues = {
        output.source_file: tuple(SubtitleCue(c.start_ms, c.end_ms, c.text) for c in output.subtitle_cues)
    }
    mapping = OriginalDialogueSubtitleMapper(source_cues).map((ResolvedSourceClip(
        segment_id=output.output_id,
        source_file=output.source_file,
        source_start_ms=output.start_ms,
        source_end_ms=output.end_ms,
        final_start_ms=0,
        final_duration_ms=output.end_ms - output.start_ms,
        source_audio=True,
    ),))
    if mapping.retained_verified_source_cue_count and not mapping.cues:
        raise ValueError("Verified Highlight dialogue could not be mapped")
    return build_srt(mapping.cues)
