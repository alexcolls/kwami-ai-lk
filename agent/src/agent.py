"""Kwami Agent - Dynamic AI agent configured by the Kwami frontend library."""

from typing import Any, Optional

from livekit.agents import Agent

from .config import KwamiConfig
from .memory import KwamiMemory
from .tools import AgentToolsMixin, ClientToolManager
from .utils.logging import get_logger
from .utils.room import should_disconnect_as_duplicate

logger = get_logger("agent")


class KwamiAgent(Agent, AgentToolsMixin):
    """Dynamic AI agent configured by the Kwami frontend library.
    
    This agent supports:
    - Configurable voice pipeline (STT, LLM, TTS)
    - Persistent memory via Zep Cloud
    - Client-side tools executed via data channel
    - Built-in tools for voice/language control
    - Dynamic reconfiguration without disconnection
    """

    def __init__(
        self,
        config: Optional[KwamiConfig] = None,
        vad: Any = None,
        memory: Optional[KwamiMemory] = None,
        stt: Any = None,
        llm: Any = None,
        tts: Any = None,
        skip_greeting: bool = False,
    ):
        """Initialize the Kwami agent.
        
        Args:
            config: Kwami configuration with persona, voice settings, etc.
            vad: Voice Activity Detection instance.
            memory: Optional Zep memory instance for persistent context.
            stt: Speech-to-Text instance.
            llm: Large Language Model instance.
            tts: Text-to-Speech instance.
            skip_greeting: If True, skip the initial greeting (for reconfigurations).
        """
        self.kwami_config = config or KwamiConfig()
        self._vad = vad
        self._memory = memory
        self._skip_greeting = skip_greeting
        self._last_memory_context = None  # Cached context from _inject_memory_context
        
        # Track current voice config for switching
        self._current_voice_config = self.kwami_config.voice
        self.room = None  # Will be set in on_enter

        # Initialize client tool manager
        self.client_tools = ClientToolManager(self)
        if self.kwami_config.tools:
            self.client_tools.register_client_tools(self.kwami_config.tools)
        
        # Build system prompt
        instructions = self._build_system_prompt()
        
        # Get client tools to pass to parent Agent
        combined_tools = self.client_tools.create_client_tools()
        self._tools = combined_tools

        super().__init__(
            instructions=instructions,
            stt=stt,
            llm=llm,
            tts=tts,
            vad=vad,
            tools=self._tools,
        )

    def _build_system_prompt(self, memory_context: Optional[str] = None) -> str:
        """Build the system prompt from persona configuration and memory context.
        
        Args:
            memory_context: Optional memory context to inject into the prompt.
            
        Returns:
            Complete system prompt string.
        """
        persona = self.kwami_config.persona
        prompt_parts = []

        # Base personality
        if persona.system_prompt:
            prompt_parts.append(persona.system_prompt)
        else:
            prompt_parts.append(f"You are {persona.name}, {persona.personality}.")

        # Traits
        if persona.traits:
            prompt_parts.append(f"\nKey traits: {', '.join(persona.traits)}")

        # Conversation style
        if persona.conversation_style:
            prompt_parts.append(f"\nConversation style: {persona.conversation_style}")

        # Response length guidance
        length_guide = {
            "short": "Keep responses brief and concise (1-2 sentences).",
            "medium": "Provide balanced responses with enough detail (2-4 sentences).",
            "long": "Give comprehensive, detailed responses when appropriate.",
        }
        if persona.response_length in length_guide:
            prompt_parts.append(f"\n{length_guide[persona.response_length]}")

        # Emotional tone guidance
        tone_guide = {
            "neutral": "Maintain a balanced, objective tone.",
            "warm": "Express warmth and friendliness in your interactions.",
            "enthusiastic": "Show enthusiasm and energy in your responses.",
            "calm": "Maintain a calm, soothing demeanor.",
        }
        if persona.emotional_tone in tone_guide:
            prompt_parts.append(f"\n{tone_guide[persona.emotional_tone]}")

        # Voice interaction guidance
        prompt_parts.append(
            "\n\nYou are interacting via voice. Keep responses concise and conversational."
        )
        prompt_parts.append(
            "Do not use emojis, asterisks, markdown, or other special characters."
        )
        prompt_parts.append("Speak naturally as if having a real conversation.")
        
        # User relationship guidance
        prompt_parts.append(
            "\nWhen users share their name, remember it and use it naturally in conversation."
        )
        prompt_parts.append("Be genuinely interested in learning about who you're talking to.")
        
        # Voice switching capability
        prompt_parts.append(
            "\nYou can change your voice or the AI model being used if the user requests it."
        )

        # Memory context injection
        if memory_context:
            prompt_parts.append("\n\n## Your Memory\n")
            prompt_parts.append(
                "You have persistent memory of past conversations with this user."
            )
            prompt_parts.append("Use this context to provide personalized responses:\n")
            prompt_parts.append(memory_context)

        return "\n".join(prompt_parts)

    async def _inject_memory_context(self) -> None:
        """Fetch memory context, cache user name, and update system prompt.
        
        Also pre-caches the user name so subsequent messages include
        proper attribution in the knowledge graph.
        """
        if not self._memory or not self._memory.is_initialized:
            return

        try:
            # Pre-cache user name for message attribution
            user_name = await self._memory.get_user_name()
            if user_name:
                logger.info(f"Cached user name from memory: {user_name}")

            context = await self._memory.get_context()
            memory_text = context.to_system_prompt_addition()
            
            if memory_text:
                new_instructions = self._build_system_prompt(memory_text)
                await self.update_instructions(new_instructions)
                logger.info("Injected memory context into system prompt")
            
            # Store context for greeting use (avoids a second API call)
            self._last_memory_context = context
        except Exception as e:
            logger.error(f"Failed to inject memory context: {e}")

    async def on_enter(self, room: Any = None) -> None:
        """Called when the agent joins the room.
        
        Args:
            room: The LiveKit room instance.
        """
        my_identity = ""
        if room:
            my_identity = room.local_participant.identity if room.local_participant else ""
            logger.info(f"Agent {my_identity} entering room...")
            
            # Quick check for duplicate agents (non-blocking)
            should_disconnect = await should_disconnect_as_duplicate(room, my_identity)
            if should_disconnect:
                logger.warning(f"Agent {my_identity} disconnecting due to duplicate detection")
                await room.disconnect()
                return
        
        # Store room reference for client tools
        self.room = room

        logger.info(
            f"Kwami agent '{self.kwami_config.kwami_name}' "
            f"({self.kwami_config.kwami_id}) entered room successfully"
        )

        # Inject memory context into system prompt
        await self._inject_memory_context()

        # Greet the user - but only once per session
        if self._skip_greeting:
            logger.debug("Skipping greeting (agent was reconfigured)")
            return
        
        # Generate a natural, personalized greeting
        try:
            logger.info("Generating greeting for user...")
            greeting_instructions = await self._build_greeting_instructions()
            self.session.generate_reply(
                instructions=greeting_instructions,
                allow_interruptions=False,
            )
        except Exception as e:
            logger.error(f"Failed to generate greeting: {e}")
            # Fall back to a simple greeting so the agent still speaks
            try:
                self.session.generate_reply(
                    instructions="Greet the user casually and ask how you can help.",
                    allow_interruptions=False,
                )
            except Exception:
                logger.error("Failed to generate fallback greeting")

    async def _build_greeting_instructions(self) -> str:
        """Build natural greeting instructions based on memory context.
        
        Reuses the context already fetched by _inject_memory_context()
        to avoid redundant API calls. Only makes a fresh call if no
        cached context is available.
        
        Returns:
            Greeting instructions for the LLM.
        """
        agent_name = (
            self.kwami_config.persona.name 
            or self.kwami_config.kwami_name 
            or "Kwami"
        )
        user_name = None
        is_returning_user = False
        recent_context_summary = None
        recent_topics = []
        
        if self._memory and self._memory.is_initialized:
            try:
                # Use cached user name (already looked up in _inject_memory_context)
                user_name = self._memory._cached_user_name
                
                # Reuse cached context from _inject_memory_context (avoids 2nd API call)
                context = self._last_memory_context
                if context is None:
                    context = await self._memory.get_context()
                
                if context.recent_messages or context.facts or context.context_block:
                    is_returning_user = True
                    logger.debug(
                        f"Returning user detected "
                        f"(messages: {len(context.recent_messages)}, facts: {len(context.facts)})"
                    )
                    
                    # Extract recent topics from context block or summary
                    if context.context_block:
                        recent_context_summary = context.context_block[:500]
                    elif context.summary:
                        recent_context_summary = context.summary
                    
                    # Get interesting facts to reference in greeting
                    if context.facts:
                        name_skip = ['name is', 'called', 'i am', "i'm"]
                        for fact in context.facts[:5]:
                            fact_lower = fact.lower()
                            if not any(skip in fact_lower for skip in name_skip):
                                recent_topics.append(fact)
                
                # If name not cached, try extracting from facts as fallback
                if not user_name and context and context.facts:
                    import re
                    for fact in context.facts:
                        match = re.search(
                            r"(?:name is|called|i'm|i am)\s+([A-Z][a-z]+)",
                            fact, re.IGNORECASE
                        )
                        if match:
                            potential = match.group(1).capitalize()
                            excluded = {'the', 'a', 'user', 'assistant', 'kwami', agent_name.lower()}
                            if potential.lower() not in excluded:
                                user_name = potential
                                self._memory.set_user_name(user_name)
                                logger.info(f"Found user name from facts: {user_name}")
                                break
                                
            except Exception as e:
                logger.warning(f"Could not extract user info from memory: {e}")
        
        # Build natural greeting instructions based on what we know
        if user_name:
            if recent_topics:
                topics_str = "; ".join(recent_topics[:3])
                return (
                    f"Greet {user_name} warmly by name, like you're happy to see them again. "
                    f"Reference something from your recent conversations naturally. "
                    f"Here's what you remember about recent topics: {topics_str}. "
                    f"Ask a casual follow-up question about one of these topics, or just ask how something is going. "
                    f"Examples: 'Hey {user_name}! How did that [project/thing] turn out?' or "
                    f"'What's up {user_name}? Been thinking about [topic] lately?' "
                    "Keep it short, friendly, and chill. Don't be formal or robotic. "
                    "Pick ONE topic and ask about it naturally - don't list everything you remember."
                )
            elif recent_context_summary:
                return (
                    f"Greet {user_name} warmly by name, like you're happy to see them again. "
                    f"Here's a summary of your past conversations: {recent_context_summary}. "
                    f"Ask a casual follow-up about something relevant, or just check in on how things are going. "
                    f"Example: 'Hey {user_name}! How's everything going?' or reference something specific. "
                    "Keep it short, friendly, and natural."
                )
            else:
                return (
                    f"Greet {user_name} casually by name, like you're happy to see them again. "
                    f"Something like 'Hey {user_name}, great to see you! What's on your mind today?' or "
                    f"'What's up {user_name}? How've you been?' "
                    "Keep it short, friendly, and chill. Don't be formal or robotic. "
                    "Don't repeat the same greeting every time - vary it naturally."
                )
        elif is_returning_user:
            return (
                f"Greet the user casually like you've talked before but can't remember their name. "
                f"Something like 'Hey there! Good to hear from you again. By the way, I'm {agent_name} - "
                "what's your name?' Keep it natural and chill."
            )
        else:
            return (
                f"Introduce yourself casually to this new user. "
                f"Something like 'Hey there! I'm {agent_name}, what's your name?' "
                "Keep it short, friendly, and natural. Don't be overly formal or give a long introduction."
            )

    async def on_user_turn_completed(self, turn_ctx: Any, new_message: Any) -> None:
        """Called when user finishes speaking.
        
        Buffers the user message so it can be sent together with the
        assistant's response in a single add_messages call. This produces
        much better knowledge graph construction in Zep.
        
        Args:
            turn_ctx: Turn context.
            new_message: The user's message.
        """
        if self._memory and self._memory.is_initialized and new_message:
            try:
                content = self._extract_message_content(new_message)
                if content:
                    # Get user name for better graph attribution
                    user_name = self._memory._cached_user_name or None
                    await self._memory.buffer_user_message(content, name=user_name)
            except Exception as e:
                logger.warning(f"Failed to buffer user message: {e}")

    async def on_agent_turn_completed(self, turn_ctx: Any, new_message: Any) -> None:
        """Called when agent finishes responding.
        
        Sends the buffered user message + this assistant response as a
        batch to Zep. Uses ignore_roles=["assistant"] so only user
        messages create graph entities, while assistant messages provide
        context for entity extraction.
        
        Args:
            turn_ctx: Turn context.
            new_message: The agent's response message.
        """
        if self._memory and self._memory.is_initialized and new_message:
            try:
                content = self._extract_message_content(new_message)
                if content:
                    agent_name = (
                        self.kwami_config.persona.name
                        or self.kwami_config.kwami_name
                    )
                    await self._memory.add_exchange(
                        assistant_content=content,
                        assistant_name=agent_name,
                    )
            except Exception as e:
                logger.warning(f"Failed to add exchange to memory: {e}")

    def _extract_message_content(self, message: Any) -> str:
        """Extract text content from various message formats.
        
        Args:
            message: Message object in various possible formats.
            
        Returns:
            Extracted text content, or empty string if extraction fails.
        """
        if message is None:
            return ""
        
        # Try common content attributes
        for attr in ("content", "text", "message"):
            if hasattr(message, attr):
                value = getattr(message, attr)
                if value is not None and isinstance(value, str) and value.strip():
                    return value.strip()
        
        # If message is already a string
        if isinstance(message, str):
            return message.strip()
        
        # Last resort: stringify but filter out object representations
        text = str(message)
        if text.startswith("<") and text.endswith(">"):
            logger.debug(f"Could not extract content from message type: {type(message)}")
            return ""
        
        return text.strip()
