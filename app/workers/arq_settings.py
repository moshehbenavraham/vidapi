from __future__ import annotations

from typing import ClassVar

from app.core.config import get_settings
from app.core.redis import get_redis_settings
from app.workers.render_worker import run_render, worker_shutdown, worker_startup


class WorkerSettings:
    """ARQ worker configuration.

    Renders are not idempotent so max_tries=1 (no automatic retries).
    job_timeout is derived from settings.render_timeout_seconds + buffer.

    Start with: arq app.workers.arq_settings.WorkerSettings
    """

    functions: ClassVar[list] = [run_render]
    on_startup = worker_startup
    on_shutdown = worker_shutdown

    max_jobs = 4
    max_tries = 1
    job_timeout = get_settings().render_timeout_seconds + 100
    health_check_interval = 30

    redis_settings = get_redis_settings()
