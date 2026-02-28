"""Built-in function tools for KwamiAgent."""

import asyncio
import json
import os
import re
from typing import Any, Dict, List, Optional

import httpx
from livekit.agents import RunContext, function_tool

from ..room_context import get_current_room
from ..utils.logging import get_logger
from ..constants import (
    CartesiaVoices,
    LANGUAGE_GREETINGS,
    TTSProviders,
)

logger = get_logger("tools")


def _extract_features(content: str, max_items: int = 8) -> List[str]:
    """Extract short feature-like phrases from snippet (apartments, products, events)."""
    if not (content or "").strip():
        return []
    # Split on newlines, bullets, dashes, semicolons, and commas (listings often use commas)
    raw = re.split(r"[\n•\-;,]+|\s+-\s+", content)
    seen: set = set()
    features: List[str] = []
    for part in raw:
        s = (part or "").strip()
        if not s or len(s) < 2:
            continue
        if len(s) > 72:
            s = s[:69] + "..."
        low = s.lower()
        if low in ("and", "or", "the", "with", "for", "from", "in", "to"):
            continue
        if low in seen:
            continue
        seen.add(low)
        features.append(s)
        if len(features) >= max_items:
            break
    return features[:max_items]


async def _fetch_image_for_url(url: str, timeout: float = 3.5) -> Optional[str]:
    """Try to get og:image or primary image for a URL via Microlink (no key required)."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(
                "https://api.microlink.io/",
                params={"url": url, "screenshot": "false", "video": "false"},
            )
            r.raise_for_status()
            data = r.json()
            d = data.get("data") or {}
            img = d.get("image")
            url_out = None
            if isinstance(img, dict) and img.get("url"):
                url_out = img["url"]
            elif isinstance(img, str) and img.startswith("http"):
                url_out = img
            if not url_out and d.get("logo"):
                logo = d.get("logo")
                if isinstance(logo, dict) and logo.get("url"):
                    url_out = logo["url"]
                elif isinstance(logo, str) and logo.startswith("http"):
                    url_out = logo
            return url_out
    except Exception as e:
        logger.debug("Microlink fetch failed for %s: %s", url[:50], e)
    return None


def _is_elevenlabs_tts(tts: Any) -> bool:
    """Check if TTS provider is ElevenLabs.
    
    Handles both the direct ElevenLabs plugin (livekit.plugins.elevenlabs)
    and LiveKit Inference TTS with an ElevenLabs model (livekit.agents.inference.tts).
    """
    provider = getattr(tts, "provider", "").lower()
    # Check the model string for "elevenlabs" (covers inference.TTS with elevenlabs model)
    model = str(getattr(tts, "_model", getattr(tts, "model", ""))).lower()
    return (
        provider == TTSProviders.ELEVENLABS
        or "elevenlabs" in type(tts).__module__
        or "elevenlabs" in model
    )


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
            
            # ElevenLabs TTS does not support speed option
            if _is_elevenlabs_tts(self.session.tts):
                return "Speed adjustment is not supported with the current ElevenLabs voice provider."
            
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

    @function_tool()
    async def web_search(self, context: RunContext, query: str, max_results: int = 5) -> str:
        """Search the web for current information. Use when the user asks about recent events, facts, news, or anything you need to look up.

        Args:
            query: The search query.
            max_results: Maximum number of results to return (1-10, default 5).
        """
        api_key = os.environ.get("TAVILY_API_KEY")
        if not api_key:
            logger.warning("TAVILY_API_KEY not set; web search disabled")
            return "Web search is not configured (missing TAVILY_API_KEY)."

        max_results = max(1, min(10, max_results))
        payload = {
            "query": query,
            "search_depth": "basic",
            "max_results": max_results,
            "include_answer": True,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    "https://api.tavily.com/search",
                    json=payload,
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as e:
            body = ""
            try:
                body = e.response.text
            except Exception:
                pass
            logger.warning(
                "Tavily search failed: status=%s body=%s",
                e.response.status_code,
                body[:500] if body else "",
            )
            if e.response.status_code == 432:
                # Don't echo Tavily's body to the user; it can be wrong (e.g. "usage limit" when credits are fine).
                # We only log it for debugging.
                return "Web search is temporarily unavailable. Please try again in a moment."
            if e.response.status_code == 401:
                return "Web search is not configured correctly (invalid API key)."
            if e.response.status_code == 429:
                return "Web search rate limit reached. Please try again in a moment."
            try:
                err = e.response.json()
                msg = err.get("detail") or err.get("message") or err.get("error") or body
            except Exception:
                msg = body or str(e)
            return f"Search failed: {msg}"
        except Exception as e:
            logger.exception("Tavily search failed")
            return f"Search failed: {str(e)}"

        results: List[Dict[str, Any]] = [
            {"title": r.get("title", ""), "url": r.get("url", ""), "content": r.get("content", "")}
            for r in data.get("results", [])
        ]
        answer = data.get("answer") or ""

        # Store search query in memory for future context
        if self._memory and self._memory.is_initialized:
            try:
                await self._memory.add_fact(f"User searched for: {query}")
            except Exception as e:
                logger.debug("Could not store search in memory: %s", e)

        # Enrich results: extract features, fetch image per result (for UI)
        max_results = 5
        max_content = 220  # Keep payload smaller so images fit under LiveKit limit
        ui_results: List[Dict[str, Any]] = []
        for r in results[:max_results]:
            content = (r.get("content") or "")[:max_content]
            features = _extract_features(content)[:5]  # Max 5 features, shorter list
            ui_results.append({
                "title": (r.get("title") or "")[:180],
                "url": (r.get("url") or "")[:400],
                "content": content,
                "features": [f[:60] for f in features],
            })

        # Fetch images in parallel (optional; don't block on failures)
        async def add_image(idx: int, url: str) -> None:
            img = await _fetch_image_for_url(url)
            if img and idx < len(ui_results):
                ui_results[idx]["image"] = (img or "")[:400]

        await asyncio.gather(*[add_image(i, r["url"]) for i, r in enumerate(ui_results)])
        images_count = sum(1 for u in ui_results if u.get("image"))
        logger.info("Fetched %s images for %s results", images_count, len(ui_results))

        room = get_current_room() or (getattr(context, "room", None) if context else None) or self.room
        if room:
            try:
                max_answer = 400
                ui_answer = (answer or "")[:max_answer]
                msg = {
                    "type": "search_results",
                    "query": query,
                    "results": ui_results,
                    "answer": ui_answer,
                }
                payload = json.dumps(msg).encode("utf-8")
                # Prefer keeping images: trim content/answer/features first, strip images only as last resort
                if len(payload) > 14 * 1024:
                    for item in msg.get("results", []):
                        item["content"] = (item.get("content") or "")[:120]
                        item["features"] = (item.get("features") or [])[:3]
                    msg["answer"] = (ui_answer or "")[:150]
                    payload = json.dumps(msg).encode("utf-8")
                if len(payload) > 14 * 1024:
                    for item in msg.get("results", []):
                        item.pop("image", None)
                    payload = json.dumps(msg).encode("utf-8")
                logger.info(
                    "Publishing search_results to room (query=%r, results=%s, with_images=%s)",
                    query[:80] if query else "",
                    len(ui_results),
                    any(u.get("image") for u in msg.get("results", [])),
                )
                await room.local_participant.publish_data(
                    payload,
                    reliable=True,
                )
                logger.info("Published search_results to client")
            except Exception as e:
                logger.warning("Failed to send search_results to client: %s", e)
        else:
            logger.warning(
                "Cannot send search_results to client: no room (self.room=%s, context.room=%s)",
                self.room is not None,
                getattr(context, "room", None) is not None if context else False,
            )

        if answer:
            return answer
        if results:
            return "\n".join(
                f"- {r['title']}: {r['content'][:150]}..." for r in results[:3]
            )
        return "No results found."
