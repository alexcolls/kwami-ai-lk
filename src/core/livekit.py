"""LiveKit utilities for token generation."""

from datetime import timedelta

from livekit.api import AccessToken, VideoGrants

from kwami_lk.core.config import settings


def create_token(
    room_name: str,
    participant_name: str,
    *,
    participant_identity: str | None = None,
    ttl: timedelta | None = None,
    can_publish: bool = True,
    can_subscribe: bool = True,
    can_publish_data: bool = True,
    can_update_own_metadata: bool = True,
    room_join: bool = True,
    room_create: bool = False,
    room_admin: bool = False,
    agent: bool = False,
) -> str:
    """
    Create a LiveKit access token.

    Args:
        room_name: Name of the room to join
        participant_name: Display name for the participant
        participant_identity: Unique identity (defaults to participant_name)
        ttl: Token time-to-live (defaults to 6 hours)
        can_publish: Allow publishing tracks
        can_subscribe: Allow subscribing to tracks
        can_publish_data: Allow publishing data messages
        can_update_own_metadata: Allow updating own metadata
        room_join: Allow joining rooms
        room_create: Allow creating rooms
        room_admin: Admin privileges
        agent: Whether this token is for an agent

    Returns:
        JWT token string
    """
    identity = participant_identity or participant_name
    token_ttl = ttl or timedelta(hours=6)

    # Create video grants
    grants = VideoGrants(
        room=room_name,
        room_join=room_join,
        room_create=room_create,
        room_admin=room_admin,
        can_publish=can_publish,
        can_subscribe=can_subscribe,
        can_publish_data=can_publish_data,
        can_update_own_metadata=can_update_own_metadata,
        agent=agent,
    )

    # Create and sign token
    token = AccessToken(
        api_key=settings.livekit_api_key,
        api_secret=settings.livekit_api_secret,
    )
    token.identity = identity
    token.name = participant_name
    token.ttl = token_ttl
    token.video_grants = grants

    return token.to_jwt()
