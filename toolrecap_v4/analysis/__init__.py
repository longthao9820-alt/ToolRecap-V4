"""ToolRecap V4 analysis models, dependencies, caching, and source preparation."""
from __future__ import annotations

from .cache import AnalysisCacheManager, default_analysis_cache_dir
from .dependencies import (
    compute_embedded_track_signature,
    compute_sidecar_signature,
    compute_source_signature,
    compute_vobsub_signature,
    hash_bytes_content,
    hash_file_content,
    is_signature_valid,
)
from .evidence_store import EvidenceCompleteness, EvidenceQueryResult, EvidenceStore
from .models import AudioSelection, DialogueReference, Evidence, PreparedEpisode, Transcript, TranscriptCue
from .scanner import ScannerChunkPolicy, ScannerConfig, ScannerProjectResult, ScannerService, compute_evidence_revision

__all__ = [
    "AnalysisCacheManager",
    "AudioSelection",
    "DialogueReference",
    "Evidence",
    "EvidenceCompleteness",
    "EvidenceQueryResult",
    "EvidenceStore",
    "PreparedEpisode",
    "Transcript",
    "TranscriptCue",
    "ScannerChunkPolicy",
    "ScannerConfig",
    "ScannerProjectResult",
    "ScannerService",
    "compute_evidence_revision",
    "compute_embedded_track_signature",
    "compute_sidecar_signature",
    "compute_source_signature",
    "compute_vobsub_signature",
    "default_analysis_cache_dir",
    "hash_bytes_content",
    "hash_file_content",
    "is_signature_valid",
]
