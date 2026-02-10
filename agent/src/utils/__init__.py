"""Utility functions for Kwami agent."""

from .logging import get_logger, log_error
from .provider import (
    strip_model_prefix,
    detect_tts_provider_from_model,
    detect_tts_provider_from_voice,
    detect_provider_change,
)
from .room import get_other_agents, should_disconnect_as_duplicate
from .validation import validate_tool_definition, normalize_config_keys

__all__ = [
    "get_logger",
    "log_error",
    "strip_model_prefix",
    "detect_tts_provider_from_model",
    "detect_tts_provider_from_voice",
    "detect_provider_change",
    "get_other_agents",
    "should_disconnect_as_duplicate",
    "validate_tool_definition",
    "normalize_config_keys",
]
