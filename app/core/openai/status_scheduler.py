from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass, field

from app.core.clients.openai_status import (
    OPENAI_STATUS_SUMMARY_URL,
    OpenAIStatusFetchError,
    fetch_openai_status,
)
from app.core.config.settings import get_settings
from app.core.openai.status_state import OpenAIStatusStore, get_openai_status_store

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class OpenAIStatusScheduler:
    """Polls the OpenAI status page and refreshes the process-local snapshot.

    Deliberately NOT leader-gated: the snapshot lives in per-process memory and
    every replica needs its own fresh copy for the dashboard endpoint and the
    error-annotation read path. The poll is a single lightweight public GET, so
    running it on every replica is cheap.
    """

    interval_seconds: int
    timeout_seconds: float
    enabled: bool
    url: str = OPENAI_STATUS_SUMMARY_URL
    _store: OpenAIStatusStore = field(default_factory=get_openai_status_store)
    _task: asyncio.Task[None] | None = None
    _stop: asyncio.Event = field(default_factory=asyncio.Event)

    async def start(self) -> None:
        if not self.enabled:
            return
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        if not self._task:
            return
        self._stop.set()
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _run_loop(self) -> None:
        while not self._stop.is_set():
            await self._refresh_once()
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval_seconds)
            except asyncio.TimeoutError:
                continue

    async def _refresh_once(self) -> None:
        try:
            snapshot = await fetch_openai_status(url=self.url, timeout_seconds=self.timeout_seconds)
        except OpenAIStatusFetchError as exc:
            # Keep the previous snapshot; staleness is derived from its age.
            self._store.record_failure()
            logger.debug("OpenAI status refresh failed: %s", exc.message)
            return
        except Exception:
            self._store.record_failure()
            logger.warning("OpenAI status refresh loop failed", exc_info=True)
            return
        self._store.record_success(snapshot)


def build_openai_status_scheduler() -> OpenAIStatusScheduler:
    settings = get_settings()
    return OpenAIStatusScheduler(
        interval_seconds=settings.openai_status_refresh_interval_seconds,
        timeout_seconds=settings.openai_status_fetch_timeout_seconds,
        enabled=settings.openai_status_enabled,
    )
