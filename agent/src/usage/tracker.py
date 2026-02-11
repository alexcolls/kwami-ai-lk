"""Usage tracker for monitoring AI resource consumption during a session.

Tracks:
- LLM token usage (prompt + completion tokens)
- STT audio duration (minutes)
- TTS character count
- Realtime model token usage
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Any

from ..utils.logging import get_logger

logger = get_logger("usage.tracker")


@dataclass
class ModelUsage:
    """Accumulated usage for a single model."""

    model_type: str  # 'llm', 'stt', 'tts', 'realtime'
    model_id: str
    total_units: float = 0.0  # tokens for LLM, minutes for STT, chars for TTS
    event_count: int = 0


def _get_model_id(metrics: Any) -> str:
    """Extract a model identifier from metrics metadata or label."""
    metadata = getattr(metrics, "metadata", None)
    if metadata:
        provider = getattr(metadata, "model_provider", None) or ""
        name = getattr(metadata, "model_name", None) or ""
        if provider and name:
            return f"{provider}/{name}"
        if name:
            return name
    return getattr(metrics, "label", None) or "unknown"


class UsageTracker:
    """Tracks AI resource consumption during a single agent session.

    Thread-safe accumulator for usage metrics from the voice pipeline.
    Call `get_usage_summary()` at session end to get the totals.
    """

    def __init__(self) -> None:
        self._usage: dict[str, ModelUsage] = {}
        self._lock = Lock()
        self._session_start = time.time()

    def _get_or_create(self, model_type: str, model_id: str) -> ModelUsage:
        """Get or create a usage entry for a model."""
        key = f"{model_type}:{model_id}"
        if key not in self._usage:
            self._usage[key] = ModelUsage(model_type=model_type, model_id=model_id)
        return self._usage[key]

    # -----------------------------------------------------------------
    # LLM tracking
    # -----------------------------------------------------------------

    def on_llm_metrics(self, metrics: Any) -> None:
        """Handle a LiveKit LLMMetrics event.

        Attributes used: prompt_tokens, completion_tokens, total_tokens, label, metadata.
        """
        model_id = _get_model_id(metrics)
        total_tokens = getattr(metrics, "total_tokens", 0)
        prompt_tokens = getattr(metrics, "prompt_tokens", 0)
        completion_tokens = getattr(metrics, "completion_tokens", 0)
        tokens = total_tokens or (prompt_tokens + completion_tokens)

        if tokens <= 0:
            return

        with self._lock:
            entry = self._get_or_create("llm", model_id)
            entry.total_units += tokens
            entry.event_count += 1

        logger.info(
            f"LLM usage: {model_id} +{tokens} tokens "
            f"(total: {entry.total_units:.0f})"
        )

    # -----------------------------------------------------------------
    # STT tracking
    # -----------------------------------------------------------------

    def on_stt_metrics(self, metrics: Any) -> None:
        """Handle a LiveKit STTMetrics event.

        Attributes used: audio_duration, label, metadata.
        """
        model_id = _get_model_id(metrics)
        audio_duration = getattr(metrics, "audio_duration", 0.0)

        if audio_duration <= 0:
            return

        minutes = audio_duration / 60.0
        with self._lock:
            entry = self._get_or_create("stt", model_id)
            entry.total_units += minutes
            entry.event_count += 1

        logger.info(
            f"STT usage: {model_id} +{minutes:.3f} min "
            f"(total: {entry.total_units:.3f} min)"
        )

    # -----------------------------------------------------------------
    # TTS tracking
    # -----------------------------------------------------------------

    def on_tts_metrics(self, metrics: Any) -> None:
        """Handle a LiveKit TTSMetrics event.

        Attributes used: characters_count, label, metadata.
        """
        model_id = _get_model_id(metrics)
        characters = getattr(metrics, "characters_count", 0)

        if characters <= 0:
            return

        with self._lock:
            entry = self._get_or_create("tts", model_id)
            entry.total_units += characters
            entry.event_count += 1

        logger.info(
            f"TTS usage: {model_id} +{characters} chars "
            f"(total: {entry.total_units:.0f} chars)"
        )

    # -----------------------------------------------------------------
    # Realtime model tracking
    # -----------------------------------------------------------------

    def on_realtime_metrics(self, metrics: Any) -> None:
        """Handle a LiveKit RealtimeModelMetrics event.

        Attributes used: total_tokens, label, metadata.
        """
        model_id = _get_model_id(metrics)
        total_tokens = getattr(metrics, "total_tokens", 0)

        if total_tokens <= 0:
            return

        with self._lock:
            entry = self._get_or_create("realtime", model_id)
            entry.total_units += total_tokens
            entry.event_count += 1

        logger.info(
            f"Realtime usage: {model_id} +{total_tokens} tokens "
            f"(total: {entry.total_units:.0f})"
        )

    # -----------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------

    def get_usage_summary(self) -> list[dict]:
        """Get the accumulated usage summary.

        Returns a list of dicts, each with:
            model_type, model_id, units_used
        """
        with self._lock:
            items = []
            for entry in self._usage.values():
                if entry.total_units > 0:
                    items.append({
                        "model_type": entry.model_type,
                        "model_id": entry.model_id,
                        "units_used": round(entry.total_units, 6),
                    })
            return items

    @property
    def session_duration_seconds(self) -> float:
        """Get the elapsed session duration in seconds."""
        return time.time() - self._session_start

    @property
    def has_usage(self) -> bool:
        """Check if any usage has been recorded."""
        with self._lock:
            return any(e.total_units > 0 for e in self._usage.values())
