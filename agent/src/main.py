"""Kwami Agent - Entry point for LiveKit Cloud agent sessions."""

import asyncio
import json
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the root directory
load_dotenv(Path(__file__).parent.parent.parent / ".env")

from livekit import rtc
from livekit.agents import (
    AgentServer,
    AgentSession,
    JobContext,
    JobProcess,
    cli,
    room_io,
)
from livekit.plugins import silero

from .agent import KwamiAgent
from .config import KwamiConfig
from .factories import create_llm, create_stt, create_tts, create_realtime_model
from .handlers import handle_full_config, handle_config_update, handle_tool_result
from .memory import create_memory
from .session import SessionState, create_session_state
from .utils.logging import get_logger

logger = get_logger()

server = AgentServer()


def prewarm(proc: JobProcess) -> None:
    """Prewarm the VAD model for faster startup."""
    proc.userdata["vad"] = silero.VAD.load()


server.setup_fnc = prewarm


@server.rtc_session(agent_name="kwami-agent")
async def entrypoint(ctx: JobContext) -> None:
    """Main entry point for Kwami agent sessions."""
    logger.info(f"Kwami session starting in room: {ctx.room.name}")

    # Log participants and extract user identity
    logger.info(f"Room has {len(ctx.room.remote_participants)} remote participants")
    user_identity = None
    for pid, p in ctx.room.remote_participants.items():
        logger.info(f"  - {p.identity} (connected: {p.is_connected})")
        if not p.identity.startswith("agent"):
            user_identity = p.identity
            logger.info(f"User identity: {user_identity}")

    # Get prewarmed VAD
    vad = ctx.proc.userdata["vad"]
    
    # Create initial agent with default configuration.
    # Skip greeting -- this is a placeholder agent until the frontend sends
    # the real config via the "config" data message. The configured agent
    # will greet properly with the correct persona, voice, and memory.
    config = KwamiConfig()
    initial_agent = create_agent_from_config(config, vad, skip_greeting=True)
    
    # Create session and state
    session = AgentSession()
    state = create_session_state(
        initial_agent=initial_agent,
        user_identity=user_identity,
        vad=vad,
    )
    
    # Setup data handler for config updates and tool results
    def handle_data(data: rtc.DataPacket) -> None:
        try:
            payload = data.data.decode("utf-8")
            message = json.loads(payload)
            msg_type = message.get("type")
            
            logger.info(f"Received data message: {msg_type}")
            
            if msg_type == "config":
                asyncio.create_task(
                    handle_full_config(
                        session, state, message, vad, create_agent_from_config
                    )
                )
            elif msg_type == "config_update":
                asyncio.create_task(
                    handle_config_update(
                        session, state, message, vad, create_agent_from_config
                    )
                )
            elif msg_type == "tool_result":
                handle_tool_result(
                    state.current_agent,
                    message.get("toolCallId"),
                    message.get("result"),
                    message.get("error"),
                )
                
        except Exception as e:
            logger.error(f"Error handling data message: {e}")

    ctx.room.on("data_received", handle_data)

    # Register cleanup for when the session ends
    ctx.add_shutdown_callback(state.cleanup)

    # Start the session
    await session.start(
        agent=initial_agent,
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=True,
            audio_output=True,
        ),
    )
    
    logger.info(f"Kwami session started for room: {ctx.room.name}")


def create_agent_from_config(
    config: KwamiConfig,
    vad,
    memory=None,
    skip_greeting: bool = False,
) -> KwamiAgent:
    """Create a KwamiAgent instance from a configuration object.
    
    Args:
        config: The Kwami configuration.
        vad: Voice Activity Detection instance.
        memory: Optional memory instance.
        skip_greeting: If True, skip the initial greeting (for reconfigurations).
        
    Returns:
        Configured KwamiAgent instance.
    """
    voice_config = config.voice
    
    if voice_config.pipeline_type == "realtime":
        logger.info(
            f"Using realtime pipeline: "
            f"{voice_config.realtime_provider}/{voice_config.realtime_model}"
        )
        realtime_model = create_realtime_model(voice_config)
        return KwamiAgent(
            config,
            vad=vad,
            memory=memory,
            llm=realtime_model,
            skip_greeting=skip_greeting,
        )
    else:
        logger.info(
            f"Using standard pipeline: "
            f"STT={voice_config.stt_provider}/{voice_config.stt_model}, "
            f"LLM={voice_config.llm_provider}/{voice_config.llm_model}, "
            f"TTS={voice_config.tts_provider}/{voice_config.tts_model}"
        )
        stt = create_stt(voice_config)
        llm = create_llm(voice_config)
        tts = create_tts(voice_config)
        return KwamiAgent(
            config,
            vad=vad,
            memory=memory,
            stt=stt,
            llm=llm,
            tts=tts,
            skip_greeting=skip_greeting,
        )


if __name__ == "__main__":
    cli.run_app(server)
