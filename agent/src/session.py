"""Session state management for Kwami agent."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

from .utils.logging import get_logger

if TYPE_CHECKING:
    from livekit.agents import AgentSession
    from .agent import KwamiAgent

logger = get_logger("session")


@dataclass
class SessionState:
    """Manages the state of a Kwami agent session.
    
    This class replaces the mutable dict pattern and provides:
    - Type-safe access to session state
    - Automatic memory cleanup when agents are replaced
    - Centralized state management
    """
    
    current_agent: Optional["KwamiAgent"] = None
    user_identity: Optional[str] = None
    vad: Any = None
    greeting_delivered: bool = False
    _cleanup_tasks: list = field(default_factory=list, repr=False)
    
    def update_agent(
        self,
        session: "AgentSession",
        new_agent: "KwamiAgent",
    ) -> None:
        """Update the current agent, cleaning up the old one's resources.
        
        Only closes memory if the new agent does NOT share the same memory
        instance (i.e. a truly new memory was created). When the same memory
        object is passed through to the new agent, closing it would break
        the new agent's memory.
        
        Args:
            session: The LiveKit agent session.
            new_agent: The new agent to switch to.
        """
        old_agent = self.current_agent
        if old_agent and old_agent._memory:
            # Only close memory if the new agent has a DIFFERENT memory instance
            new_memory = getattr(new_agent, "_memory", None)
            if new_memory is not old_agent._memory:
                cleanup_task = asyncio.create_task(
                    self._cleanup_memory(old_agent._memory)
                )
                self._cleanup_tasks.append(cleanup_task)
        
        # Update the session with the new agent
        session.update_agent(new_agent)
        self.current_agent = new_agent
        
        logger.debug(f"Agent updated, cleanup tasks pending: {len(self._cleanup_tasks)}")
    
    async def _cleanup_memory(self, memory: Any) -> None:
        """Clean up memory resources in the background.
        
        Args:
            memory: The KwamiMemory instance to clean up.
        """
        try:
            if hasattr(memory, "close"):
                await memory.close()
                logger.debug("Old agent memory closed successfully")
        except Exception as e:
            logger.warning(f"Failed to close memory: {e}")
    
    async def cleanup(self) -> None:
        """Clean up all pending resources.
        
        Should be called when the session ends.
        """
        # Wait for all cleanup tasks to complete
        if self._cleanup_tasks:
            await asyncio.gather(*self._cleanup_tasks, return_exceptions=True)
            self._cleanup_tasks.clear()
        
        # Clean up current agent's memory
        if self.current_agent and self.current_agent._memory:
            await self._cleanup_memory(self.current_agent._memory)
        
        logger.debug("Session cleanup complete")
    
    @property
    def has_agent(self) -> bool:
        """Check if there's a current agent."""
        return self.current_agent is not None
    
    def get_agent_or_none(self) -> Optional["KwamiAgent"]:
        """Get the current agent if it exists."""
        return self.current_agent


def create_session_state(
    initial_agent: "KwamiAgent",
    user_identity: Optional[str] = None,
    vad: Any = None,
) -> SessionState:
    """Factory function to create a SessionState.
    
    Args:
        initial_agent: The initial KwamiAgent instance.
        user_identity: Optional user identity string.
        vad: Optional VAD instance.
        
    Returns:
        Configured SessionState instance.
    """
    return SessionState(
        current_agent=initial_agent,
        user_identity=user_identity,
        vad=vad,
    )
