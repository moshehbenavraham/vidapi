from __future__ import annotations

import pytest

from app.core.config import Settings
from app.db import render_crud
from app.db.render_crud import (
    RendererFailureCount,
    RenderStatusCount,
    RenderTimingSample,
)
from app.db.webhook_crud import WebhookOutcomeCount
from app.models.render import RenderStatus
from app.services.metrics import (
    MetricsSnapshot,
    QueueMetric,
    collect_metrics_snapshot,
    collect_queue_metric,
    format_prometheus_metrics,
)


class FakeRedisPool:
    def __init__(self, depth: int) -> None:
        self.depth = depth
        self.queue_name: str | None = None

    async def llen(self, queue_name: str) -> int:
        self.queue_name = queue_name
        return self.depth


def test_format_prometheus_metrics_is_deterministic_and_redacted() -> None:
    snapshot = MetricsSnapshot(
        render_status_counts=[
            RenderStatusCount(status="failed", count=2),
            RenderStatusCount(status="queued", count=1),
        ],
        renderer_failure_counts=[
            RendererFailureCount(
                renderer='editly"main',
                error_code="RENDER_ERROR",
                count=2,
            )
        ],
        webhook_outcome_counts=[
            WebhookOutcomeCount(
                webhook_event="render.failed",
                outcome="failure",
                count=3,
            )
        ],
        queue_wait_samples=[RenderTimingSample(render_id="render_a", seconds=1.25)],
        render_duration_samples=[RenderTimingSample(render_id="render_a", seconds=4.5)],
        queue=QueueMetric(available=True, depth=7),
    )

    text = format_prometheus_metrics(snapshot)

    assert 'vidapi_render_status_total{status="failed"} 2' in text
    assert 'vidapi_renderer_failures_total{renderer="editly\\"main"' in text
    assert 'webhook_event="render.failed",outcome="failure"} 3' in text
    assert "vidapi_queue_available 1" in text
    assert "vidapi_queue_depth 7" in text
    assert "vidapi_queue_wait_seconds_count 1" in text
    assert "vidapi_queue_wait_seconds_sum 1.25" in text
    assert "render_a" not in text


@pytest.mark.asyncio
async def test_collect_metrics_snapshot_handles_sync_queue_mode(db_session) -> None:
    render = await render_crud.create_render(db_session)
    await render_crud.update_render_status(db_session, render.id, RenderStatus.FETCHING)
    await render_crud.update_render_status(
        db_session, render.id, RenderStatus.COMPILING
    )
    await render_crud.update_render_status(
        db_session, render.id, RenderStatus.RENDERING
    )
    await render_crud.update_render_status(
        db_session, render.id, RenderStatus.UPLOADING
    )
    await render_crud.update_render_status(
        db_session, render.id, RenderStatus.SUCCEEDED
    )

    snapshot = await collect_metrics_snapshot(
        db_session,
        settings=Settings(render_mode="sync"),
        arq_pool=None,
    )
    text = format_prometheus_metrics(snapshot)

    assert snapshot.queue.available is False
    assert snapshot.queue.error == "sync_mode"
    assert "vidapi_queue_available 0" in text
    assert 'vidapi_queue_unavailable_info{reason="sync_mode"} 1' in text
    assert 'vidapi_render_status_total{status="succeeded"} 1' in text
    assert "vidapi_queue_wait_seconds_count 1" in text
    assert "vidapi_render_duration_seconds_count 1" in text


@pytest.mark.asyncio
async def test_collect_queue_metric_handles_missing_and_available_redis() -> None:
    async_settings = Settings(render_mode="async")

    missing = await collect_queue_metric(settings=async_settings, arq_pool=None)
    assert missing.available is False
    assert missing.depth is None
    assert missing.error == "redis_unavailable"

    fake_pool = FakeRedisPool(depth=9)
    available = await collect_queue_metric(
        settings=async_settings,
        arq_pool=fake_pool,
    )
    assert available.available is True
    assert available.depth == 9
    assert fake_pool.queue_name == async_settings.redis_queue_name
