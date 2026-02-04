from livekit.plugins import deepgram, openai

try:
    from livekit.plugins import assemblyai
except ImportError:
    assemblyai = None  # type: ignore

try:
    from livekit.plugins import google
except ImportError:
    google = None  # type: ignore

try:
    from livekit.plugins import elevenlabs
except ImportError:
    elevenlabs = None  # type: ignore

from ..config import KwamiVoiceConfig
from ..constants import (
    STTProviders,
    OpenAIModels,
    DeepgramModels,
)
from ..utils.logging import get_logger

logger = get_logger("stt")


def create_stt(config: KwamiVoiceConfig):
    """Create STT instance based on configuration."""
    provider = config.stt_provider.lower()
    
    logger.info(f"🎤 Creating STT: provider={provider}, model={config.stt_model}")
    
    if provider == STTProviders.DEEPGRAM:
        return deepgram.STT(
            model=config.stt_model or DeepgramModels.DEFAULT_STT,
            language=config.stt_language,
            interim_results=True,
            smart_format=True,
            punctuate=True,
        )
    
    elif provider == STTProviders.OPENAI:
        return openai.STT(
            model=config.stt_model or OpenAIModels.WHISPER_1,
            language=config.stt_language if config.stt_language != "multi" else None,
        )
    
    elif provider == STTProviders.ASSEMBLYAI and assemblyai is not None:
        return assemblyai.STT(
            word_boost=config.stt_word_boost or [],
        )
    
    elif provider == STTProviders.GOOGLE and google is not None:
        return google.STT(
            model=config.stt_model or "chirp",
            languages=[config.stt_language or "en-US"],
        )
    
    elif provider == STTProviders.ELEVENLABS and elevenlabs is not None:
        return elevenlabs.STT(
            model=config.stt_model or "scribe_v1",
            language=config.stt_language or "en",
        )
    
    else:
        logger.warning(f"Unknown or unavailable STT provider '{provider}', falling back to Deepgram")
        return deepgram.STT(
            model=DeepgramModels.DEFAULT_STT,
            language="en",
        )
