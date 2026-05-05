from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.core.config import Settings
from app.core.security import hash_api_key
from app.models.composition import Composition
from app.services.ffprobe import MediaInfo
from app.services.limits import (
    LimitExceededError,
    summarize_composition,
    validate_composition_limits,
    validate_media_limits,
)
from app.services.queue_admission import QueueSaturatedError, admit_render_queue

VALID_API_KEY_HASH = hash_api_key("vidapi-limit-test-key")


def _composition(
    *,
    length: float = 3.0,
    width: int = 1920,
    height: int = 1080,
    fps: int = 30,
    tracks: int = 1,
    clips_per_track: int = 1,
) -> Composition:
    return Composition.model_validate(
        {
            "timeline": {
                "tracks": [
                    {
                        "clips": [
                            {
                                "asset": {
                                    "type": "image",
                                    "src": f"https://example.com/{t}-{c}.png",
                                },
                                "start": float(c) * length,
                                "length": length,
                            }
                            for c in range(clips_per_track)
                        ]
                    }
                    for t in range(tracks)
                ]
            },
            "output": {
                "format": "mp4",
                "width": width,
                "height": height,
                "fps": fps,
            },
        }
    )


def _production_settings(**overrides: object) -> Settings:
    base = {
        "environment": "production",
        "database_url": "postgresql+asyncpg://user:pass@localhost/vidapi",
        "database_auto_create": False,
        "api_key_auth_enabled": True,
        "api_key_hashes": [VALID_API_KEY_HASH],
    }
    base.update(overrides)
    return Settings(**base)


def test_production_async_redis_requires_tls() -> None:
    with pytest.raises(ValueError, match="rediss://"):
        _production_settings(
            render_mode="async",
            redis_url="redis://:redis-pass@localhost:6379/0",
        )


def test_production_async_redis_requires_auth() -> None:
    with pytest.raises(ValueError, match="REDIS_URL credentials"):
        _production_settings(
            render_mode="async",
            redis_url="rediss://localhost:6379/0",
        )


def test_production_async_redis_accepts_tls_and_auth() -> None:
    settings = _production_settings(
        render_mode="async",
        redis_url="rediss://:redis-pass@localhost:6379/0",
    )

    assert settings.redis_url.startswith("rediss://")


def test_summarize_composition_counts_tracks_clips_assets_and_duration() -> None:
    composition = _composition(length=2.0, tracks=2, clips_per_track=2)

    stats = summarize_composition(composition)

    assert stats.track_count == 2
    assert stats.clip_count == 4
    assert stats.asset_count == 4
    assert stats.duration_seconds == 4.0


def test_composition_duration_limit_rejected() -> None:
    composition = _composition(length=5.0)
    settings = Settings(max_render_duration_seconds=4)

    with pytest.raises(LimitExceededError) as exc_info:
        validate_composition_limits(composition, settings)

    violation = exc_info.value.violation
    assert violation.code == "COMPOSITION_LIMIT_EXCEEDED"
    assert violation.field == "timeline.duration"
    assert violation.limit == 4
    assert violation.observed == 5.0


def test_composition_asset_count_limit_rejected() -> None:
    composition = _composition(tracks=2, clips_per_track=2)
    settings = Settings(max_assets_per_render=3)

    with pytest.raises(LimitExceededError) as exc_info:
        validate_composition_limits(composition, settings)

    assert exc_info.value.violation.field == "timeline.assets"


def test_html_payload_limit_rejected() -> None:
    composition = Composition.model_validate(
        {
            "timeline": {
                "tracks": [
                    {
                        "clips": [
                            {
                                "asset": {
                                    "type": "html",
                                    "html": "<div>" + ("x" * 2048) + "</div>",
                                },
                                "length": 1.0,
                            }
                        ]
                    }
                ]
            }
        }
    )
    settings = Settings(max_html_asset_bytes=1024)

    with pytest.raises(LimitExceededError) as exc_info:
        validate_composition_limits(composition, settings)

    assert exc_info.value.violation.field.endswith(".asset.html")


def test_media_duration_and_stream_limits_rejected() -> None:
    media_info = MediaInfo(
        duration=30.0,
        width=1920,
        height=1080,
        video_codec="h264",
        audio_codec="aac",
        stream_count=4,
        format_name="mov,mp4",
    )
    settings = Settings(max_media_duration_seconds=10, max_media_streams_per_asset=2)

    with pytest.raises(LimitExceededError) as exc_info:
        validate_media_limits(media_info, settings)

    assert exc_info.value.violation.field == "media.duration"


@pytest.mark.asyncio
async def test_queue_admission_rejects_saturated_queue() -> None:
    pool = AsyncMock()
    pool.llen = AsyncMock(return_value=5)
    settings = Settings(render_mode="async", max_async_queue_depth=5)

    with pytest.raises(QueueSaturatedError) as exc_info:
        await admit_render_queue(settings=settings, arq_pool=pool)

    assert exc_info.value.depth == 5
    assert exc_info.value.max_depth == 5
    pool.llen.assert_awaited_once_with(settings.redis_queue_name)
