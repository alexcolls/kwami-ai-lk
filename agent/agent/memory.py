"""Zep Cloud Memory Integration for Kwami Agents.

Provides persistent, per-Kwami memory using Zep Cloud's memory platform.
Each Kwami maintains independent memory through unique user IDs.

Features:
- Automatic conversation history tracking
- Fact extraction and knowledge graph building
- Temporal context retrieval (sub-200ms)
- Independent memory isolation per Kwami instance
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from .config import KwamiMemoryConfig

# Lazy imports for zep_cloud - only imported when memory is actually used
if TYPE_CHECKING:
    from zep_cloud.client import AsyncZep

logger = logging.getLogger("kwami-memory")


def _get_zep_imports():
    """Lazy import zep_cloud to avoid startup errors when not using memory."""
    try:
        from zep_cloud.client import AsyncZep
        from zep_cloud.types import Message as ZepMessage
        from zep_cloud.types import RoleType
        return AsyncZep, ZepMessage, RoleType
    except ImportError as e:
        logger.error(f"Failed to import zep_cloud: {e}")
        logger.error("Install with: pip install zep-cloud")
        return None, None, None


@dataclass
class MemoryContext:
    """Context retrieved from Zep memory for LLM injection."""

    summary: Optional[str] = None
    facts: list[str] = None
    entities: list[dict] = None
    recent_messages: list[dict] = None

    def __post_init__(self):
        self.facts = self.facts or []
        self.entities = self.entities or []
        self.recent_messages = self.recent_messages or []

    def to_system_prompt_addition(self) -> str:
        """Convert memory context to text for system prompt injection."""
        parts = []

        if self.summary:
            parts.append(f"## Conversation Summary\n{self.summary}")

        if self.facts:
            facts_text = "\n".join(f"- {fact}" for fact in self.facts)
            parts.append(f"## Known Facts About User\n{facts_text}")

        if self.entities:
            entities_text = "\n".join(
                f"- {e.get('name', 'Unknown')}: {e.get('type', 'entity')}"
                for e in self.entities
            )
            parts.append(f"## Relevant Entities\n{entities_text}")

        if not parts:
            return ""

        return "\n\n".join(parts)


class KwamiMemory:
    """Memory manager for a single Kwami instance.

    Handles all Zep interactions for persistent memory, including:
    - User and session management
    - Message persistence
    - Context retrieval
    - Fact and entity extraction
    """

    def __init__(self, config: KwamiMemoryConfig, kwami_id: str, kwami_name: str = "Kwami"):
        self.config = config
        self.kwami_id = kwami_id
        self.kwami_name = kwami_name
        self._client: Optional[AsyncZep] = None
        self._user_id: Optional[str] = None
        self._session_id: Optional[str] = None
        self._initialized = False

    @property
    def is_enabled(self) -> bool:
        """Check if memory is enabled and configured."""
        return self.config.enabled and bool(self.config.api_key)

    @property
    def is_initialized(self) -> bool:
        """Check if memory has been initialized."""
        return self._initialized

    @property
    def user_id(self) -> Optional[str]:
        """Get the Zep user ID for this Kwami."""
        return self._user_id

    @property
    def session_id(self) -> Optional[str]:
        """Get the current Zep session ID."""
        return self._session_id

    async def initialize(self) -> bool:
        """Initialize the Zep client and ensure user/session exist.

        Returns:
            True if initialization succeeded, False otherwise.
        """
        if not self.is_enabled:
            logger.warning("Memory is disabled or API key not configured")
            return False

        # Lazy import zep_cloud
        AsyncZep, _, _ = _get_zep_imports()
        if AsyncZep is None:
            logger.error("zep_cloud not available, disabling memory")
            return False

        try:
            # Create Zep client
            self._client = AsyncZep(api_key=self.config.api_key)

            # Set user_id - use kwami_id for independent memory per Kwami
            self._user_id = self.config.user_id or f"kwami_{self.kwami_id}"

            # Ensure user exists in Zep
            await self._ensure_user_exists()

            # Set or create session
            self._session_id = self.config.session_id or f"session_{self._user_id}_{uuid.uuid4().hex[:8]}"

            # Ensure session exists
            await self._ensure_session_exists()

            self._initialized = True
            logger.info(
                f"🧠 Memory initialized for Kwami '{self.kwami_name}' "
                f"(user: {self._user_id}, session: {self._session_id})"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to initialize memory: {e}")
            self._initialized = False
            return False

    async def _ensure_user_exists(self) -> None:
        """Create user in Zep if it doesn't exist.
        
        Note: The Zep "user" represents the HUMAN user, not the AI assistant.
        The kwami_name is stored in metadata for reference but NOT as the user's
        first_name, which would confuse Zep's entity extraction.
        """
        try:
            await self._client.user.get(self._user_id)
            logger.debug(f"User {self._user_id} already exists")
        except Exception:
            # User doesn't exist, create it
            try:
                await self._client.user.add(
                    user_id=self._user_id,
                    metadata={
                        "kwami_id": self.kwami_id,
                        "assistant_name": self.kwami_name,  # AI assistant name (for reference only)
                        "created_at": datetime.utcnow().isoformat(),
                    },
                    # Don't set first_name to kwami_name - that would confuse Zep's
                    # entity extraction since the "user" should be the human, not the AI
                    first_name="User",
                )
                logger.info(f"Created Zep user: {self._user_id}")
            except Exception as e:
                # Handle race condition where user was created by another process
                error_msg = str(e).lower()
                if "400" in error_msg and "already exists" in error_msg:
                    logger.info(f"User {self._user_id} already exists (race condition handled)")
                    return
                logger.error(f"Failed to create user {self._user_id}: {e}")
                # Don't raise, just log error - memory might still work if user exists
                # But if it truly failed, maybe we should disable memory?
                # For now, let's keep it robust.
                raise

    async def _ensure_session_exists(self) -> None:
        """Create thread (session) in Zep if it doesn't exist.
        
        Note: Zep Cloud v3 uses 'thread' instead of 'session' terminology.
        """
        try:
            await self._client.thread.get(thread_id=self._session_id)
            logger.debug(f"Thread {self._session_id} already exists")
        except Exception:
            # Thread doesn't exist, create it
            try:
                await self._client.thread.create(
                    thread_id=self._session_id,
                    user_id=self._user_id,
                )
                logger.info(f"Created Zep thread: {self._session_id}")
            except Exception as e:
                logger.error(f"Failed to create thread {self._session_id}: {e}")
                raise

    async def add_message(self, role: str, content: str) -> None:
        """Add a message to memory.

        Args:
            role: Message role - 'user' or 'assistant'
            content: Message content
        """
        if not self._initialized or not self._client:
            logger.debug("Memory not initialized, skipping add_message")
            return

        if not content or not content.strip():
            logger.debug("Empty content, skipping add_message")
            return

        try:
            _, ZepMessage, RoleType = _get_zep_imports()
            if ZepMessage is None:
                logger.warning("ZepMessage not available, skipping add_message")
                return

            # Normalize role to lowercase
            role = role.lower().strip()
            if role not in ("user", "assistant", "system"):
                logger.warning(f"Unknown role '{role}', defaulting to 'user'")
                role = "user"

            # Create message with simple string role (Zep SDK v3 format)
            # The SDK accepts role as a string directly
            message = ZepMessage(
                role=role,
                content=content.strip(),
            )

            await self._client.thread.add_messages(
                thread_id=self._session_id,
                messages=[message],
            )

            logger.debug(f"Added {role} message to memory: {content[:50]}...")

        except Exception as e:
            # Log full error for debugging
            import traceback
            logger.error(
                f"Failed to add message to memory: {type(e).__name__}: {e}\n"
                f"Role: {role}, Content length: {len(content)}\n"
                f"Traceback: {traceback.format_exc()}"
            )

    async def get_context(self) -> MemoryContext:
        """Get memory context for LLM injection.

        Returns:
            MemoryContext with summary, facts, entities, and recent messages.
        """
        if not self._initialized or not self._client:
            return MemoryContext()

        try:
            context = MemoryContext()

            # Get thread context (summary and relevant info)
            try:
                thread_context = await self._client.thread.get_context(
                    thread_id=self._session_id,
                    min_score=self.config.min_fact_relevance,
                )
                if thread_context and thread_context.context:
                    context.summary = thread_context.context
            except Exception as e:
                logger.debug(f"Could not retrieve thread context: {e}")

            # Get recent messages from thread
            try:
                messages_response = await self._client.thread.get_messages(
                    thread_id=self._session_id,
                    limit=self.config.max_context_messages,
                )
                if messages_response and messages_response.messages:
                    context.recent_messages = [
                        {
                            "role": msg.role or msg.role_type,
                            "content": msg.content,
                        }
                        for msg in messages_response.messages
                    ]
            except Exception as e:
                logger.debug(f"Could not retrieve thread messages: {e}")

            # Get user facts if enabled (using graph search in Zep v3)
            if self.config.include_facts:
                try:
                    # Zep v3 stores facts on graph edges - search for them
                    facts_response = await self._client.graph.search(
                        user_id=self._user_id,
                        query="user information facts preferences",
                        scope="edges",
                        limit=20,
                    )
                    if facts_response and facts_response.edges:
                        context.facts = [
                            edge.fact for edge in facts_response.edges 
                            if hasattr(edge, 'fact') and edge.fact
                        ]
                except Exception as e:
                    logger.debug(f"Could not retrieve user facts via graph: {e}")
                    # Fallback: try deprecated get_facts for older Zep versions
                    try:
                        facts_response = await self._client.user.get_facts(self._user_id)
                        if facts_response and hasattr(facts_response, 'facts') and facts_response.facts:
                            context.facts = [
                                f.fact for f in facts_response.facts if hasattr(f, 'fact') and f.fact
                            ]
                    except Exception:
                        pass  # Silently fail if neither method works

            logger.debug(
                f"Retrieved context: {len(context.facts)} facts, "
                f"{len(context.recent_messages)} messages"
            )
            return context

        except Exception as e:
            logger.error(f"Failed to get memory context: {e}")
            return MemoryContext()

    async def search(self, query: str, limit: int = 5) -> list[dict]:
        """Search memory for relevant context.

        Args:
            query: Search query
            limit: Maximum number of results

        Returns:
            List of search results with content and score.
        """
        if not self._initialized or not self._client:
            return []

        try:
            results = await self._client.thread.search(
                thread_id=self._session_id,
                query=query,
                limit=limit,
            )

            return [
                {
                    "content": r.message.content if hasattr(r, "message") and r.message else (r.content if hasattr(r, "content") else ""),
                    "score": r.score if hasattr(r, "score") else 0,
                    "thread_id": self._session_id,
                }
                for r in (results.results if hasattr(results, "results") else results or [])
            ]

        except Exception as e:
            logger.error(f"Failed to search memory: {e}")
            return []

    async def add_fact(self, fact: str) -> None:
        """Add a fact about the user.

        In Zep Cloud v3, facts are automatically extracted from messages.
        This method adds the fact as a system message so it gets processed
        and added to the user's knowledge graph.

        Args:
            fact: The fact to add (e.g., "User's name is Alex")
        """
        if not self._initialized or not self._client:
            return

        try:
            # Zep v3 extracts facts from messages automatically
            # Add as a system message to trigger fact extraction
            _, ZepMessage, _ = _get_zep_imports()
            if ZepMessage is None:
                logger.warning("ZepMessage not available, skipping add_fact")
                return
            
            # Frame the fact as a statement that Zep can extract
            message = ZepMessage(
                role="system",
                content=f"Important information learned: {fact}",
            )
            
            await self._client.thread.add_messages(
                thread_id=self._session_id,
                messages=[message],
            )
            logger.info(f"Added fact as system message: {fact}")
        except Exception as e:
            logger.error(f"Failed to add fact: {e}")

    async def clear_session(self) -> None:
        """Clear the current thread (session) memory."""
        if not self._initialized or not self._client:
            return

        try:
            await self._client.thread.delete(thread_id=self._session_id)
            logger.info(f"Cleared thread memory: {self._session_id}")
        except Exception as e:
            logger.error(f"Failed to clear thread: {e}")

    async def close(self) -> None:
        """Close the Zep client connection."""
        if self._client:
            try:
                await self._client.close()
            except Exception:
                pass
            self._client = None
        self._initialized = False
        logger.debug("Memory client closed")

    def build_memory_enhanced_prompt(self, base_prompt: str) -> str:
        """Build system prompt with memory context injection.
        
        Note: This is a sync method for simple prompt building.
        For full context, use get_context() and to_system_prompt_addition().
        
        Args:
            base_prompt: The original system prompt
            
        Returns:
            Enhanced prompt with memory context placeholder
        """
        if not self.config.auto_inject_context:
            return base_prompt
            
        return (
            f"{base_prompt}\n\n"
            "## Memory Context\n"
            "You have access to your persistent memory about past conversations. "
            "Use this context to provide personalized, contextual responses.\n"
            "{{MEMORY_CONTEXT}}"
        )


async def create_memory(
    config: KwamiMemoryConfig,
    kwami_id: str,
    kwami_name: str = "Kwami",
) -> Optional[KwamiMemory]:
    """Factory function to create and initialize a KwamiMemory instance.

    Args:
        config: Memory configuration
        kwami_id: Unique identifier for the Kwami
        kwami_name: Display name for the Kwami

    Returns:
        Initialized KwamiMemory instance, or None if initialization fails.
    """
    memory = KwamiMemory(config, kwami_id, kwami_name)

    if not memory.is_enabled:
        logger.info(f"Memory disabled for Kwami '{kwami_name}'")
        return None

    if await memory.initialize():
        return memory

    return None
