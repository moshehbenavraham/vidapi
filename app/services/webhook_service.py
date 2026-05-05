from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from typing import Any

import httpx
import structlog

from app.core.config import Settings, get_settings
from app.core.logging import safe_log_excerpt
from app.db import render_crud, webhook_crud
from app.db.models import Render
from app.models.output_artifacts import (
    RenderCaptionMetadata,
    RenderOutputMetadata,
    RenderPosterMetadata,
    caption_metadata_from_render,
    output_metadata_from_render,
    poster_metadata_from_render,
)
from app.storage.factory import build_storage, build_storage_url_resolver
from app.storage.urls import StorageUrlResolver

logger = structlog.get_logger(__name__)


def build_webhook_payload(
    *,
    event: str,
    render: Render,
    url: str | None = None,
    poster: str | None = None,
    output: RenderOutputMetadata | None = None,
    captions: RenderCaptionMetadata | None = None,
    poster_metadata: RenderPosterMetadata | None = None,
) -> dict[str, Any]:
    """Construct the PRD-specified webhook payload as a plain dict.

    Pure function with no side effects -- suitable for direct testing.
    """
    if url is None and render.output_path:
        url = f"/v1/renders/{render.id}/download"

    if poster is None and render.poster_path:
        poster = f"/v1/renders/{render.id}/poster"

    completed_at: str | None = None
    if render.completed_at is not None:
        completed_at = render.completed_at.isoformat()

    output_metadata = output or output_metadata_from_render(render)
    caption_metadata = captions or caption_metadata_from_render(render)
    poster_metadata_value = poster_metadata or poster_metadata_from_render(
        render,
        poster_url=poster,
    )

    return {
        "event": event,
        "render_id": render.id,
        "status": render.status,
        "url": url,
        "poster": poster,
        "output": (
            output_metadata.model_dump(mode="json")
            if output_metadata is not None
            else None
        ),
        "captions": (
            caption_metadata.model_dump(mode="json")
            if caption_metadata is not None
            else None
        ),
        "poster_metadata": (
            poster_metadata_value.model_dump(mode="json")
            if poster_metadata_value is not None
            else None
        ),
        "completed_at": completed_at,
    }


async def build_storage_aware_webhook_payload(
    *,
    event: str,
    render: Render,
    url_resolver: StorageUrlResolver,
) -> dict[str, Any]:
    """Construct a webhook payload with storage-aware artifact URLs."""
    output_metadata_resolver = getattr(url_resolver, "output_metadata", None)
    output = (
        await output_metadata_resolver(render)
        if output_metadata_resolver is not None
        else output_metadata_from_render(render)
    )
    caption_metadata_resolver = getattr(url_resolver, "caption_metadata", None)
    captions = (
        await caption_metadata_resolver(render)
        if caption_metadata_resolver is not None
        else caption_metadata_from_render(render)
    )
    poster_metadata_resolver = getattr(url_resolver, "poster_metadata", None)
    poster_metadata = (
        await poster_metadata_resolver(render)
        if poster_metadata_resolver is not None
        else poster_metadata_from_render(render)
    )
    return build_webhook_payload(
        event=event,
        render=render,
        url=await url_resolver.output_url(render),
        poster=await url_resolver.poster_url(render),
        output=output,
        captions=captions,
        poster_metadata=poster_metadata,
    )


def sign_payload(payload_bytes: bytes, secret: str) -> tuple[str, str]:
    """Produce HMAC-SHA256 signature and timestamp for a payload.

    Returns (signature_hex, timestamp_str).
    """
    timestamp = str(int(time.time()))
    message = f"{timestamp}.".encode("ascii") + payload_bytes
    signature = hmac.new(
        secret.encode("utf-8"),
        message,
        hashlib.sha256,
    ).hexdigest()
    return signature, timestamp


def build_headers(
    payload_bytes: bytes,
    secret: str | None,
) -> dict[str, str]:
    """Build outbound headers including HMAC signature when secret is set."""
    headers: dict[str, str] = {
        "Content-Type": "application/json",
    }
    if secret:
        sig, ts = sign_payload(payload_bytes, secret)
        headers["X-VidAPI-Signature"] = sig
        headers["X-VidAPI-Timestamp"] = ts
    return headers


async def _deliver_single_attempt(
    *,
    client: httpx.AsyncClient,
    url: str,
    payload_bytes: bytes,
    headers: dict[str, str],
    timeout: float,
    session_factory: Any,
    render_id: str,
    event: str,
    attempt_number: int,
) -> bool:
    """Execute one HTTP POST and record the attempt in the DB.

    Returns True if delivery succeeded (2xx), False otherwise.
    """
    async with session_factory() as db_session:
        attempt = await webhook_crud.create_attempt(
            db_session,
            render_id=render_id,
            event=event,
            url=url,
            attempt_number=attempt_number,
        )
        attempt_id = attempt.id
        if attempt_id is None:
            raise RuntimeError("Webhook attempt was not assigned an id")

    status_code: int | None = None
    response_excerpt: str | None = None
    error_msg: str | None = None
    success = False

    try:
        response = await client.post(
            url,
            content=payload_bytes,
            headers=headers,
            timeout=timeout,
        )
        status_code = response.status_code
        response_excerpt = response.text[:500] if response.text else None
        success = 200 <= status_code < 300

    except httpx.TimeoutException as exc:
        error_msg = f"Timeout: {exc}"
    except httpx.ConnectError as exc:
        error_msg = f"Connection error: {exc}"
    except httpx.HTTPError as exc:
        error_msg = f"HTTP error: {exc}"
    except Exception as exc:
        error_msg = f"Unexpected error: {type(exc).__name__}: {exc}"

    async with session_factory() as db_session:
        await webhook_crud.update_attempt_result(
            db_session,
            attempt_id,
            status_code=status_code,
            response_body_excerpt=response_excerpt,
            error=error_msg,
        )

    if success:
        await logger.ainfo(
            "webhook_delivered",
            render_id=render_id,
            webhook_event=event,
            attempt=attempt_number,
            outcome="success",
            status_code=status_code,
        )
    else:
        await logger.awarning(
            "webhook_attempt_failed",
            render_id=render_id,
            webhook_event=event,
            attempt=attempt_number,
            outcome="failure",
            status_code=status_code,
            error_excerpt=safe_log_excerpt(error_msg),
            response_body_excerpt=safe_log_excerpt(response_excerpt),
        )

    return success


async def deliver_with_retries(
    *,
    url: str,
    payload_bytes: bytes,
    headers: dict[str, str],
    session_factory: Any,
    render_id: str,
    event: str,
    settings: Settings | None = None,
) -> bool:
    """Deliver a webhook with exponential backoff retries.

    Returns True if any attempt succeeded. Each attempt is recorded
    individually in the webhook_attempts table.
    """
    if settings is None:
        settings = get_settings()

    max_retries = settings.webhook_max_retries
    retry_delays = settings.webhook_retry_delays
    timeout = float(settings.webhook_timeout_seconds)

    async with httpx.AsyncClient() as client:
        for attempt_num in range(1, max_retries + 1):
            success = await _deliver_single_attempt(
                client=client,
                url=url,
                payload_bytes=payload_bytes,
                headers=headers,
                timeout=timeout,
                session_factory=session_factory,
                render_id=render_id,
                event=event,
                attempt_number=attempt_num,
            )
            if success:
                return True

            if attempt_num < max_retries:
                delay_index = attempt_num - 1
                delay = (
                    retry_delays[delay_index]
                    if delay_index < len(retry_delays)
                    else retry_delays[-1]
                )
                await logger.ainfo(
                    "webhook_retry_scheduled",
                    render_id=render_id,
                    webhook_event=event,
                    delay_seconds=delay,
                    next_attempt=attempt_num + 1,
                )
                await asyncio.sleep(delay)

    await logger.aerror(
        "webhook_delivery_exhausted",
        render_id=render_id,
        webhook_event=event,
        total_attempts=max_retries,
    )
    return False


async def dispatch_webhook(
    *,
    session_factory: Any,
    render_id: str,
    event: str,
) -> None:
    """Top-level webhook dispatch: read render, build payload, deliver.

    This function catches ALL exceptions to guarantee webhook failures
    never propagate to the render pipeline.
    """
    try:
        async with session_factory() as db_session:
            render = await render_crud.get_render_by_id(db_session, render_id)

        if render is None:
            await logger.awarning(
                "webhook_render_not_found",
                render_id=render_id,
                webhook_event=event,
            )
            return

        callback_url = render.callback_url
        if not callback_url:
            return

        settings = get_settings()
        storage = build_storage(settings)
        url_resolver = build_storage_url_resolver(
            settings=settings,
            storage=storage,
        )
        payload = await build_storage_aware_webhook_payload(
            event=event,
            render=render,
            url_resolver=url_resolver,
        )
        payload_bytes = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        headers = build_headers(
            payload_bytes,
            settings.webhook_secret or None,
        )

        await deliver_with_retries(
            url=callback_url,
            payload_bytes=payload_bytes,
            headers=headers,
            session_factory=session_factory,
            render_id=render_id,
            event=event,
            settings=settings,
        )

    except Exception:
        await logger.aexception(
            "webhook_dispatch_error",
            render_id=render_id,
            webhook_event=event,
        )
