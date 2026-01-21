"""
Kwami Agent - LiveKit Cloud Agent

Entry point for the Kwami AI agent deployed to LiveKit Cloud.
Run locally with: uv run python agent.py dev
Deploy with: lk agent deploy
"""

import asyncio
import json
import logging
from typing import Any, Optional

from livekit import rtc
from livekit.agents import Agent, AgentServer, AgentSession, JobContext, RunContext, function_tool, room_io

from config import KwamiConfig
from plugins import create_llm, create_stt, create_tts, create_vad

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kwami-agent")

server = AgentServer()


class KwamiAgent(Agent):
    """Dynamic AI agent configured by the Kwami frontend library."""

    def __init__(self, config: Optional[KwamiConfig] = None):
        self.kwami_config = config or KwamiConfig()
        self._tasks: list[asyncio.Task] = []

        instructions = self._build_system_prompt()
        super().__init__(instructions=instructions)

    def _build_system_prompt(self) -> str:
        """Build the system prompt from persona configuration."""
        persona = self.kwami_config.persona

        prompt_parts = []

        if persona.system_prompt:
            prompt_parts.append(persona.system_prompt)
        else:
            prompt_parts.append(f"You are {persona.name}, {persona.personality}.")

        if persona.traits:
            prompt_parts.append(f"\nKey traits: {', '.join(persona.traits)}")

        if persona.conversation_style:
            prompt_parts.append(f"\nConversation style: {persona.conversation_style}")

        length_guide = {
            "short": "Keep responses brief and concise (1-2 sentences).",
            "medium": "Provide balanced responses with enough detail (2-4 sentences).",
            "long": "Give comprehensive, detailed responses when appropriate.",
        }
        if persona.response_length in length_guide:
            prompt_parts.append(f"\n{length_guide[persona.response_length]}")

        tone_guide = {
            "neutral": "Maintain a balanced, objective tone.",
            "warm": "Express warmth and friendliness in your interactions.",
            "enthusiastic": "Show enthusiasm and energy in your responses.",
            "calm": "Maintain a calm, soothing demeanor.",
        }
        if persona.emotional_tone in tone_guide:
            prompt_parts.append(f"\n{tone_guide[persona.emotional_tone]}")

        return "\n".join(prompt_parts)

    async def on_enter(self):
        """Called when the agent joins the room."""
        room = self.session.room
        room.on("data_received", self._handle_data_message)

        logger.info(
            f"🤖 Kwami agent '{self.kwami_config.kwami_name}' "
            f"({self.kwami_config.kwami_id}) entered room"
        )

    async def _handle_data_message(
        self,
        data: bytes,
        participant: rtc.RemoteParticipant,
        kind: rtc.DataPacketKind,
        topic: Optional[str],
    ):
        """Handle incoming data messages from the frontend."""
        try:
            message = json.loads(data.decode("utf-8"))
            msg_type = message.get("type")

            if msg_type == "config":
                await self._apply_full_config(message)
            elif msg_type == "config_update":
                update_type = message.get("updateType")
                config = message.get("config")

                if update_type == "persona":
                    await self._update_persona(config)
                elif update_type == "voice":
                    await self._update_voice(config)
                elif update_type == "tools":
                    await self._update_tools(config)
                elif update_type == "full":
                    await self._apply_full_config(config)
            elif msg_type == "interrupt":
                await self._handle_interrupt()

        except json.JSONDecodeError:
            logger.warning("Received invalid JSON data message")
        except Exception as e:
            logger.error(f"Error handling data message: {e}")

    async def _apply_full_config(self, config: dict):
        """Apply full Kwami configuration."""
        logger.info(f"Applying full config for Kwami: {config.get('kwamiId', 'unknown')}")

        self.kwami_config.kwami_id = config.get("kwamiId", "")
        self.kwami_config.kwami_name = config.get("kwamiName", "Kwami")

        if "persona" in config:
            await self._update_persona(config["persona"])
        if "voice" in config:
            await self._update_voice(config["voice"])
        if "tools" in config:
            await self._update_tools(config["tools"])

        logger.info(f"✅ Config applied for Kwami '{self.kwami_config.kwami_name}'")

    async def _update_persona(self, persona_config: dict):
        """Update persona configuration dynamically."""
        persona = self.kwami_config.persona

        if "name" in persona_config:
            persona.name = persona_config["name"]
        if "personality" in persona_config:
            persona.personality = persona_config["personality"]
        if "systemPrompt" in persona_config:
            persona.system_prompt = persona_config["systemPrompt"]
        if "traits" in persona_config:
            persona.traits = persona_config["traits"]
        if "language" in persona_config:
            persona.language = persona_config["language"]
        if "conversationStyle" in persona_config:
            persona.conversation_style = persona_config["conversationStyle"]
        if "responseLength" in persona_config:
            persona.response_length = persona_config["responseLength"]
        if "emotionalTone" in persona_config:
            persona.emotional_tone = persona_config["emotionalTone"]

        new_instructions = self._build_system_prompt()
        await self.update_instructions(new_instructions)

        logger.info(f"📝 Updated persona for '{persona.name}'")

    async def _update_voice(self, voice_config: dict):
        """Update voice pipeline configuration dynamically."""
        voice = self.kwami_config.voice

        if "stt" in voice_config:
            stt = voice_config["stt"]
            if "provider" in stt:
                voice.stt_provider = stt["provider"]
            if "model" in stt:
                voice.stt_model = stt["model"]
            if "language" in stt:
                voice.stt_language = stt["language"]

        if "llm" in voice_config:
            llm_cfg = voice_config["llm"]
            if "provider" in llm_cfg:
                voice.llm_provider = llm_cfg["provider"]
            if "model" in llm_cfg:
                voice.llm_model = llm_cfg["model"]
            if "temperature" in llm_cfg:
                voice.llm_temperature = llm_cfg["temperature"]

        if "tts" in voice_config:
            tts = voice_config["tts"]
            if "provider" in tts:
                voice.tts_provider = tts["provider"]
            if "voice" in tts:
                voice.tts_voice = tts["voice"]
            if "model" in tts:
                voice.tts_model = tts["model"]
            if "speed" in tts:
                voice.tts_speed = tts["speed"]

        if "vad" in voice_config:
            vad = voice_config["vad"]
            if "provider" in vad:
                voice.vad_provider = vad["provider"]
            if "threshold" in vad:
                voice.vad_threshold = vad["threshold"]

        if "enhancements" in voice_config:
            enh = voice_config["enhancements"]
            if "noiseCancellation" in enh:
                voice.noise_cancellation = enh["noiseCancellation"]["enabled"]
            if "turnDetection" in enh:
                voice.turn_detection = enh["turnDetection"]["mode"]

        logger.info(f"🎙️ Updated voice config: LLM={voice.llm_model}, TTS={voice.tts_voice}")

    async def _update_tools(self, tools_config: list):
        """Update tools configuration dynamically."""
        self.kwami_config.tools = tools_config
        logger.info(f"🔧 Updated tools: {len(tools_config)} tools registered")

    async def _handle_interrupt(self):
        """Handle interrupt signal from frontend."""
        logger.info("⚡ Interrupt received from frontend")

    @function_tool()
    async def get_kwami_info(self, context: RunContext) -> dict[str, Any]:
        """Get information about this Kwami instance."""
        return {
            "kwami_id": self.kwami_config.kwami_id,
            "kwami_name": self.kwami_config.kwami_name,
            "persona": {
                "name": self.kwami_config.persona.name,
                "personality": self.kwami_config.persona.personality,
            },
        }


@server.rtc_session()
async def kwami_session(ctx: JobContext):
    """Main entry point for Kwami agent sessions."""
    logger.info(f"🚀 Kwami session starting in room: {ctx.room.name}")

    config = KwamiConfig()
    agent = KwamiAgent(config)

    session = AgentSession(
        stt=create_stt(config.voice),
        llm=create_llm(config.voice),
        tts=create_tts(config.voice),
        vad=create_vad(config.voice),
    )

    await session.start(
        agent=agent,
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=True,
            audio_output=True,
            noise_cancellation=(
                room_io.NoiseFilter.BVC if config.voice.noise_cancellation else None
            ),
        ),
    )

    logger.info(f"✅ Kwami session started for room: {ctx.room.name}")


if __name__ == "__main__":
    server.run()
