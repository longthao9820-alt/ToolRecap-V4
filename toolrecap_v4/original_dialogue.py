"""Authoritative source-dialogue to final-timeline subtitle mapping.

The same mapper is used by Recap and Highlight.  It operates only on verified
source transcript cues and the resolved edit timeline; narration, audio gain,
and VoiceStudio settings never affect eligibility.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from toolrecap_v4.analysis.models import PreparedEpisode
from toolrecap_v4.subtitles import SubtitleCue

ORIGINAL_DIALOGUE_MAPPED = "ORIGINAL_DIALOGUE_MAPPED"
NO_ORIGINAL_DIALOGUE = "NO_ORIGINAL_DIALOGUE"
ORIGINAL_SUBTITLE_GENERATION_FAILED = "ORIGINAL_SUBTITLE_GENERATION_FAILED"


@dataclass(frozen=True)
class ResolvedSourceClip:
    segment_id: str
    source_file: str
    source_start_ms: int
    source_end_ms: int
    final_start_ms: int
    final_duration_ms: int
    source_audio: bool = True

    def __post_init__(self) -> None:
        if self.source_start_ms < 0 or self.source_end_ms <= self.source_start_ms:
            raise ValueError("Resolved source clip requires valid source bounds")
        if self.final_start_ms < 0 or self.final_duration_ms <= 0:
            raise ValueError("Resolved source clip requires valid final-timeline bounds")


@dataclass(frozen=True)
class OriginalDialogueMapping:
    cues: tuple[SubtitleCue, ...]
    state: str
    retained_verified_source_cue_count: int


def source_dialogue_map_from_episodes(
    episodes: Sequence[PreparedEpisode],
) -> dict[str, tuple[SubtitleCue, ...]]:
    """Index normalized verified transcript cues by exact source basename."""
    result: dict[str, tuple[SubtitleCue, ...]] = {}
    for episode in episodes:
        basename = episode.source_basename or episode.source_path.name
        result[basename] = tuple(
            SubtitleCue(cue.start_ms, cue.end_ms, cue.text.strip())
            for cue in episode.transcript.cues
            if cue.end_ms > cue.start_ms and cue.text.strip()
        )
    return result


class OriginalDialogueSubtitleMapper:
    """Clip, shift, globally sort, and renumber verified source dialogue."""

    def __init__(self, source_cues: Mapping[str, Sequence[SubtitleCue | Mapping[str, Any]]]) -> None:
        self.source_cues = {
            source: tuple(
                cue if isinstance(cue, SubtitleCue) else SubtitleCue.from_dict(dict(cue))
                for cue in cues
            )
            for source, cues in source_cues.items()
        }

    def map(self, clips: Sequence[ResolvedSourceClip]) -> OriginalDialogueMapping:
        mapped: list[SubtitleCue] = []
        retained = 0
        for clip in clips:
            if not clip.source_audio:
                continue
            final_end = clip.final_start_ms + clip.final_duration_ms
            for cue in self.source_cues.get(clip.source_file, ()):
                overlap_start = max(cue.start_ms, clip.source_start_ms)
                overlap_end = min(cue.end_ms, clip.source_end_ms)
                if overlap_end <= overlap_start:
                    continue
                retained += 1
                mapped_start = clip.final_start_ms + overlap_start - clip.source_start_ms
                mapped_end = clip.final_start_ms + overlap_end - clip.source_start_ms
                # A held final frame adds no source audio/dialogue.  This clamp
                # also protects against rounding beyond the resolved segment.
                mapped_end = min(mapped_end, final_end)
                if mapped_end > mapped_start:
                    mapped.append(SubtitleCue(mapped_start, mapped_end, cue.text))
        mapped.sort(key=lambda cue: (cue.start_ms, cue.end_ms, cue.text))
        if retained and not mapped:
            return OriginalDialogueMapping((), ORIGINAL_SUBTITLE_GENERATION_FAILED, retained)
        return OriginalDialogueMapping(
            tuple(mapped),
            ORIGINAL_DIALOGUE_MAPPED if mapped else NO_ORIGINAL_DIALOGUE,
            retained,
        )


def normalize_spoken_text(value: str) -> str:
    return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in value).split())


def narration_contains_source_dialogue(narration: str, dialogue_texts: Sequence[str]) -> bool:
    """Reject source speech routed into TTS, including quoted dialogue."""
    normalized_narration = normalize_spoken_text(narration)
    if not normalized_narration:
        return False
    for text in dialogue_texts:
        normalized_dialogue = normalize_spoken_text(text)
        if len(normalized_dialogue) >= 4 and normalized_dialogue in normalized_narration:
            return True
    return False
