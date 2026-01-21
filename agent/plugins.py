"""Factory functions for creating agent pipeline components."""

from livekit.plugins import cartesia, deepgram, openai, silero

from config import KwamiVoiceConfig


def create_stt(config: KwamiVoiceConfig):
    """Create STT instance based on configuration."""
    if config.stt_provider == "deepgram":
        return deepgram.STT(
            model=config.stt_model,
            language=config.stt_language,
        )
    return deepgram.STT()


def create_llm(config: KwamiVoiceConfig):
    """Create LLM instance based on configuration."""
    if config.llm_provider == "openai":
        return openai.LLM(
            model=config.llm_model,
            temperature=config.llm_temperature,
        )
    return openai.LLM()


def create_tts(config: KwamiVoiceConfig):
    """Create TTS instance based on configuration."""
    if config.tts_provider == "cartesia":
        return cartesia.TTS(
            voice=config.tts_voice,
            model=config.tts_model,
            speed=config.tts_speed,
        )
    elif config.tts_provider == "openai":
        return openai.TTS(
            voice=config.tts_voice,
        )
    return cartesia.TTS()


def create_vad(config: KwamiVoiceConfig):
    """Create VAD instance based on configuration."""
    return silero.VAD.load(
        min_speech_duration=config.vad_min_speech_duration,
        min_silence_duration=config.vad_min_silence_duration,
    )
