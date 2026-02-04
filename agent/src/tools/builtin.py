"""Built-in function tools for KwamiAgent."""

from typing import Any, Dict

from livekit.agents import RunContext, function_tool

from ..utils.logging import get_logger
from ..constants import (
    CartesiaVoices,
    LANGUAGE_GREETINGS,
    TTSProviders,
)

logger = get_logger("tools")


def _is_elevenlabs_tts(tts: Any) -> bool:
    """Check if TTS provider is ElevenLabs."""
    provider = getattr(tts, "provider", "").lower()
    return provider == TTSProviders.ELEVENLABS or "elevenlabs" in type(tts).__module__


class AgentToolsMixin:
    """Mixin containing function tools for KwamiAgent.
    
    This mixin assumes the following attributes exist on the class:
    - kwami_config: KwamiConfig instance
    - _current_voice_config: KwamiVoiceConfig instance
    - _memory: Optional KwamiMemory instance
    - session: AgentSession with tts and stt attributes
    """

    @function_tool()
    async def get_kwami_info(self, context: RunContext) -> Dict[str, Any]:
        """Get information about this Kwami instance."""
        return {
            "kwami_id": self.kwami_config.kwami_id,
            "kwami_name": self.kwami_config.kwami_name,
            "persona": {
                "name": self.kwami_config.persona.name,
                "personality": self.kwami_config.persona.personality,
            },
        }

    @function_tool()
    async def get_current_time(self, context: RunContext) -> str:
        """Get the current time. Useful when the user asks what time it is."""
        from datetime import datetime
        return datetime.now().strftime("%I:%M %p on %A, %B %d, %Y")

    @function_tool()
    async def change_voice(self, context: RunContext, voice_name: str) -> str:
        """Change the TTS voice. Available voices depend on the current TTS provider.
        
        Args:
            voice_name: The name or ID of the voice to switch to.
                       For Cartesia: Use voice names like 'British Lady', 'California Girl', etc.
                       For ElevenLabs: Use voice names like 'Rachel', 'Josh', 'Bella', etc.
                       For OpenAI: Use 'alloy', 'echo', 'nova', 'shimmer', 'onyx', 'fable'.
        """
        try:
            if not hasattr(self, "session") or self.session is None:
                return "Unable to change voice - session not available"
            
            if self.session.tts is None:
                return "Unable to change voice - TTS not available"
            
            # Check if it's a known name and convert to ID
            voice_id = CartesiaVoices.NAME_MAP.get(voice_name.lower(), voice_name)
            
            # Different TTS providers use different parameter names
            if _is_elevenlabs_tts(self.session.tts):
                self.session.tts.update_options(voice_id=voice_id)
            else:
                self.session.tts.update_options(voice=voice_id)
            
            logger.info(f"Voice changed to: {voice_name}")
            return f"Voice changed to {voice_name}. I'm now speaking with a different voice!"
            
        except Exception as e:
            logger.error(f"Failed to change voice: {e}")
            return f"Sorry, I couldn't change the voice: {str(e)}"

    @function_tool()
    async def change_speaking_speed(self, context: RunContext, speed: float) -> str:
        """Change the speaking speed. 
        
        Args:
            speed: Speed multiplier between 0.5 (slow) and 2.0 (fast). 
                   1.0 is normal speed.
        """
        try:
            if not hasattr(self, "session") or self.session is None:
                return "Unable to change speed - session not available"
            
            if self.session.tts is None:
                return "Unable to change speed - TTS not available"
            
            speed = max(0.5, min(2.0, speed))  # Clamp to valid range
            self.session.tts.update_options(speed=speed)
            logger.info(f"Speaking speed changed to: {speed}")
            
            if speed < 0.8:
                return f"Speed set to {speed}. I'll speak more slowly now."
            elif speed > 1.2:
                return f"Speed set to {speed}. I'll speak faster now."
            else:
                return f"Speed set to {speed}. Speaking at normal pace."
                
        except Exception as e:
            logger.error(f"Failed to change speed: {e}")
            return f"Sorry, I couldn't change the speed: {str(e)}"

    @function_tool()
    async def change_language(self, context: RunContext, language: str) -> str:
        """Change the conversation language for both speech recognition and synthesis.
        
        Args:
            language: Language code like 'en' (English), 'es' (Spanish), 'fr' (French),
                     'de' (German), 'it' (Italian), 'pt' (Portuguese), 'ja' (Japanese),
                     'ko' (Korean), 'zh' (Chinese).
        """
        try:
            if not hasattr(self, "session") or self.session is None:
                return f"Language preference noted: {language}"
            
            language = language.lower().strip()
            
            # Update STT language
            if self.session.stt is not None:
                self.session.stt.update_options(language=language)
                logger.info(f"STT language changed to: {language}")
            
            # Update TTS language if supported
            if self.session.tts is not None:
                try:
                    self.session.tts.update_options(language=language)
                    logger.info(f"TTS language changed to: {language}")
                except Exception:
                    pass  # Not all TTS providers support language parameter
            
            return LANGUAGE_GREETINGS.get(language, f"Language changed to {language}.")
            
        except Exception as e:
            logger.error(f"Failed to change language: {e}")
            return f"Sorry, I couldn't change the language: {str(e)}"

    @function_tool()
    async def get_current_voice_settings(self, context: RunContext) -> Dict[str, Any]:
        """Get the current voice pipeline settings."""
        voice_config = self._current_voice_config
        return {
            "tts_provider": voice_config.tts_provider,
            "tts_model": voice_config.tts_model,
            "tts_voice": voice_config.tts_voice,
            "tts_speed": voice_config.tts_speed,
            "stt_provider": voice_config.stt_provider,
            "stt_model": voice_config.stt_model,
            "stt_language": voice_config.stt_language,
            "llm_provider": voice_config.llm_provider,
            "llm_model": voice_config.llm_model,
            "llm_temperature": voice_config.llm_temperature,
        }

    @function_tool()
    async def remember_fact(self, context: RunContext, fact: str) -> str:
        """Remember an important fact about the user for future conversations."""
        if not self._memory or not self._memory.is_initialized:
            return "Memory is not available in this session."
        
        try:
            await self._memory.add_fact(fact)
            logger.info(f"Remembered fact: {fact}")
            return f"I'll remember that: {fact}"
        except Exception as e:
            logger.error(f"Failed to remember fact: {e}")
            return "Sorry, I couldn't save that to memory."

    @function_tool()
    async def recall_memories(self, context: RunContext, topic: str) -> str:
        """Search your memory for information about a specific topic."""
        if not self._memory or not self._memory.is_initialized:
            return "Memory is not available in this session."
        
        try:
            results = await self._memory.search(topic, limit=5)
            
            if not results:
                return f"I don't have any memories about '{topic}' yet."
            
            memories = []
            for r in results:
                if r.get("content"):
                    memories.append(f"- {r['content']}")
            
            if memories:
                return f"Here's what I remember about '{topic}':\n" + "\n".join(memories)
            return f"I don't have specific memories about '{topic}'."
            
        except Exception as e:
            logger.error(f"Failed to recall memories: {e}")
            return "Sorry, I couldn't search my memory right now."

    @function_tool()
    async def get_memory_status(self, context: RunContext) -> Dict[str, Any]:
        """Get the current memory status and statistics."""
        if not self._memory:
            return {
                "enabled": False,
                "status": "Memory not configured",
            }
        
        if not self._memory.is_initialized:
            return {
                "enabled": True,
                "status": "Memory not initialized",
            }
        
        try:
            memory_context = await self._memory.get_context()
            return {
                "enabled": True,
                "status": "Active",
                "user_id": self._memory.user_id,
                "session_id": self._memory.session_id,
                "facts_count": len(memory_context.facts),
                "recent_messages_count": len(memory_context.recent_messages),
                "has_summary": memory_context.summary is not None,
            }
        except Exception as e:
            return {
                "enabled": True,
                "status": f"Error: {str(e)}",
            }
