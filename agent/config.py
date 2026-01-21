"""Kwami agent configuration types."""

from dataclasses import dataclass, field


@dataclass
class KwamiPersonaConfig:
    """Persona configuration from the Kwami frontend."""

    name: str = "Kwami"
    personality: str = "A friendly and helpful AI companion"
    system_prompt: str = ""
    traits: list[str] = field(default_factory=list)
    language: str = "en"
    conversation_style: str = "friendly"
    response_length: str = "medium"  # short, medium, long
    emotional_tone: str = "warm"  # neutral, warm, enthusiastic, calm


@dataclass
class KwamiVoiceConfig:
    """Voice pipeline configuration from the Kwami frontend."""

    # STT
    stt_provider: str = "deepgram"
    stt_model: str = "nova-2"
    stt_language: str = "en"

    # LLM
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o"
    llm_temperature: float = 0.8

    # TTS
    tts_provider: str = "cartesia"
    tts_voice: str = "79a125e8-cd45-4c13-8a67-188112f4dd22"
    tts_model: str = "sonic"
    tts_speed: float = 1.0

    # VAD
    vad_provider: str = "silero"
    vad_threshold: float = 0.5
    vad_min_speech_duration: float = 0.1
    vad_min_silence_duration: float = 0.3

    # Enhancements
    noise_cancellation: bool = True
    turn_detection: str = "server_vad"

    # Pipeline type
    pipeline_type: str = "voice"


@dataclass
class KwamiConfig:
    """Full Kwami configuration received from frontend."""

    kwami_id: str = ""
    kwami_name: str = "Kwami"
    persona: KwamiPersonaConfig = field(default_factory=KwamiPersonaConfig)
    voice: KwamiVoiceConfig = field(default_factory=KwamiVoiceConfig)
    tools: list[dict] = field(default_factory=list)
