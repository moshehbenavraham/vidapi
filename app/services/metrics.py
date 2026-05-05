from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db import render_crud, webhook_crud
from app.db.render_crud import RenderTimingSample

TIMING_SAMPLE_LIMIT = 100
QUEUE_DEPTH_ATTEMPTS = 2
QUEUE_DEPTH_BACKOFF_SECONDS = 0.1


@dataclass(frozen=True)
class QueueMetric:
    available: bool
    depth: int | None
    error: str | None = None


@dataclass(frozen=True)
class MetricsSnapshot:
    render_status_counts: list[render_crud.RenderStatusCount]
    renderer_failure_counts: list[render_crud.RendererFailureCount]
    webhook_outcome_counts: list[webhook_crud.WebhookOutcomeCount]
    queue_wait_samples: list[RenderTimingSample]
    render_duration_samples: list[RenderTimingSample]
    queue: QueueMetric


async def collect_metrics_snapshot(
    session: AsyncSession,
    *,
    settings: Settings,
    arq_pool: Any | None = None,
) -> MetricsSnapshot:
    """Collect a bounded operational metrics snapshot."""
    queue_metric = await collect_queue_metric(settings=settings, arq_pool=arq_pool)
    return MetricsSnapshot(
        render_status_counts=await render_crud.count_renders_by_status(session),
        renderer_failure_counts=await render_crud.count_renderer_failures(session),
        webhook_outcome_counts=await webhook_crud.count_webhook_outcomes(session),
        queue_wait_samples=await render_crud.list_queue_wait_samples(
            session,
            limit=TIMING_SAMPLE_LIMIT,
        ),
        render_duration_samples=await render_crud.list_render_duration_samples(
            session,
            limit=TIMING_SAMPLE_LIMIT,
        ),
        queue=queue_metric,
    )


async def collect_queue_metric(
    *,
    settings: Settings,
    arq_pool: Any | None,
) -> QueueMetric:
    """Return Redis queue depth with bounded timeout and retry behavior."""
    if settings.render_mode != "async":
        return QueueMetric(available=False, depth=None, error="sync_mode")
    if arq_pool is None:
        return QueueMetric(available=False, depth=None, error="redis_unavailable")

    last_error: str | None = None
    timeout = settings.queue_admission_timeout_seconds
    for attempt in range(QUEUE_DEPTH_ATTEMPTS):
        try:
            depth = await asyncio.wait_for(
                arq_pool.llen(settings.redis_queue_name),
                timeout=timeout,
            )
            return QueueMetric(available=True, depth=int(depth))
        except TimeoutError:
            last_error = "timeout"
        except Exception as exc:
            last_error = type(exc).__name__

        if attempt < QUEUE_DEPTH_ATTEMPTS - 1:
            await asyncio.sleep(QUEUE_DEPTH_BACKOFF_SECONDS * (attempt + 1))

    return QueueMetric(available=False, depth=None, error=last_error or "unknown")


def format_prometheus_metrics(snapshot: MetricsSnapshot) -> str:
    """Format metrics as deterministic Prometheus text exposition."""
    lines: list[str] = [
        "# HELP vidapi_render_status_total Current renders grouped by status.",
        "# TYPE vidapi_render_status_total gauge",
    ]
    for count in snapshot.render_status_counts:
        lines.append(
            f'vidapi_render_status_total{{status="{_label(count.status)}"}} '
            f"{count.count}"
        )

    lines.extend(
        [
            "# HELP vidapi_renderer_failures_total "
            "Failed renders by renderer and code.",
            "# TYPE vidapi_renderer_failures_total gauge",
        ]
    )
    for count in snapshot.renderer_failure_counts:
        lines.append(
            "vidapi_renderer_failures_total"
            f'{{renderer="{_label(count.renderer)}",'
            f'error_code="{_label(count.error_code)}"}} {count.count}'
        )

    lines.extend(
        [
            "# HELP vidapi_webhook_attempts_total "
            "Webhook attempts by event and outcome.",
            "# TYPE vidapi_webhook_attempts_total gauge",
        ]
    )
    for count in snapshot.webhook_outcome_counts:
        lines.append(
            "vidapi_webhook_attempts_total"
            f'{{webhook_event="{_label(count.webhook_event)}",'
            f'outcome="{_label(count.outcome)}"}} {count.count}'
        )

    lines.extend(
        [
            "# HELP vidapi_queue_available "
            "Whether Redis queue depth could be observed.",
            "# TYPE vidapi_queue_available gauge",
            f"vidapi_queue_available {1 if snapshot.queue.available else 0}",
            "# HELP vidapi_queue_depth Current ARQ queue depth.",
            "# TYPE vidapi_queue_depth gauge",
            "vidapi_queue_depth "
            f"{snapshot.queue.depth if snapshot.queue.depth is not None else 0}",
        ]
    )
    if snapshot.queue.error is not None:
        lines.extend(
            [
                "# HELP vidapi_queue_unavailable_info Queue unavailable reason.",
                "# TYPE vidapi_queue_unavailable_info gauge",
                "vidapi_queue_unavailable_info"
                f'{{reason="{_label(snapshot.queue.error)}"}} 1',
            ]
        )

    lines.extend(
        _format_timing_summary(
            "vidapi_queue_wait_seconds",
            snapshot.queue_wait_samples,
        )
    )
    lines.extend(
        _format_timing_summary(
            "vidapi_render_duration_seconds",
            snapshot.render_duration_samples,
        )
    )
    return "\n".join(lines) + "\n"


def _format_timing_summary(name: str, samples: list[RenderTimingSample]) -> list[str]:
    values = [sample.seconds for sample in samples]
    total = sum(values)
    maximum = max(values, default=0.0)
    return [
        f"# HELP {name} Bounded recent timing sample summary.",
        f"# TYPE {name} summary",
        f"{name}_count {len(values)}",
        f"{name}_sum {_float(total)}",
        f"{name}_max {_float(maximum)}",
    ]


def _label(value: str) -> str:
    return value[:100].replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _float(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".") if value else "0"
