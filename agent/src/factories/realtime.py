from livekit.plugins import openai

try:
    from livekit.plugins import google
except ImportError:
    google = None  # type: ignore

from ..config import KwamiVoiceConfig
from ..utils.provider import strip_model_prefix


def create_realtime_model(config: KwamiVoiceConfig):
    """Create Realtime model instance for ultra-low latency."""
    provider = config.realtime_provider.lower() if config.realtime_provider else "openai"
    
    # Strip provider prefix from model name
    model = strip_model_prefix(config.realtime_model or "", provider)
    
    if provider == "openai":
        return openai.realtime.RealtimeModel(
            model=model or "gpt-4o-realtime-preview",
            voice=config.realtime_voice or "alloy",
            temperature=config.llm_temperature,
            modalities=config.realtime_modalities or ["text", "audio"],
            turn_detection=openai.realtime.ServerVadOptions(
                threshold=config.vad_threshold,
                prefix_padding_ms=300,
                silence_duration_ms=int(config.vad_min_silence_duration * 1000),
            ),
        )
    
    elif provider == "google" and google is not None:
        return google.beta.realtime.RealtimeModel(
            model=model or "gemini-2.0-flash-exp",
            voice=config.realtime_voice or "Puck",
            temperature=config.llm_temperature,
        )
    
    # Default to OpenAI Realtime
    return openai.realtime.RealtimeModel(
        model="gpt-4o-realtime-preview",
        voice="alloy",
    )
