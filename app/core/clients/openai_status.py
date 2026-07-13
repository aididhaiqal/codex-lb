from __future__ import annotations

import asyncio
import logging
from datetime import datetime

import aiohttp
from aiohttp_retry import ExponentialRetry, RetryClient
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.clients.http import lease_retry_client
from app.core.openai.status_state import (
    OpenAIStatusComponent,
    OpenAIStatusIncident,
    OpenAIStatusSnapshot,
)
from app.core.types import JsonObject
from app.core.utils.request_id import get_request_id
from app.core.utils.time import utcnow

logger = logging.getLogger(__name__)

# Statuspage summary endpoint: overall indicator + components + unresolved incidents.
OPENAI_STATUS_SUMMARY_URL = "https://status.openai.com/api/v2/summary.json"
DEFAULT_TIMEOUT_SECONDS = 5.0

# Statuspage incident statuses that mean the incident is over.
_RESOLVED_INCIDENT_STATUSES = frozenset({"resolved", "postmortem", "completed"})


class OpenAIStatusFetchError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class _SummaryStatus(BaseModel):
    model_config = ConfigDict(extra="ignore")

    indicator: str = "none"
    description: str = ""


class _SummaryComponent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = ""
    name: str = ""
    status: str = "operational"


class _SummaryIncidentComponent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = ""
    name: str = ""


class _SummaryIncident(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = ""
    name: str = ""
    impact: str = "none"
    status: str = "investigating"
    started_at: datetime | None = None
    shortlink: str | None = None
    components: list[_SummaryIncidentComponent] = Field(default_factory=list)


class _Summary(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: _SummaryStatus = Field(default_factory=_SummaryStatus)
    components: list[_SummaryComponent] = Field(default_factory=list)
    incidents: list[_SummaryIncident] = Field(default_factory=list)


def _is_unresolved(status: str) -> bool:
    return status.strip().lower() not in _RESOLVED_INCIDENT_STATUSES


def parse_openai_status_summary(
    data: JsonObject,
    *,
    fetched_at: datetime | None = None,
) -> OpenAIStatusSnapshot:
    """Parse a Statuspage ``summary.json`` body into an immutable snapshot.

    Pure and lenient: unknown fields are ignored and only unresolved incidents
    are retained. Raises ``pydantic.ValidationError`` only on a structurally
    invalid payload (e.g. wrong container types).
    """
    summary = _Summary.model_validate(data)
    components = tuple(
        OpenAIStatusComponent(id=component.id, name=component.name, status=component.status)
        for component in summary.components
        if component.name
    )
    incidents = tuple(
        OpenAIStatusIncident(
            id=incident.id,
            name=incident.name,
            impact=incident.impact,
            status=incident.status,
            started_at=incident.started_at,
            shortlink=incident.shortlink,
            component_names=tuple(component.name for component in incident.components if component.name),
        )
        for incident in summary.incidents
        if _is_unresolved(incident.status)
    )
    return OpenAIStatusSnapshot(
        indicator=summary.status.indicator or "none",
        description=summary.status.description,
        components=components,
        incidents=incidents,
        fetched_at=fetched_at or utcnow(),
    )


async def fetch_openai_status(
    *,
    url: str = OPENAI_STATUS_SUMMARY_URL,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    client: RetryClient | None = None,
) -> OpenAIStatusSnapshot:
    """GET the OpenAI status summary and parse it into a snapshot.

    Raises ``OpenAIStatusFetchError`` on any transport, HTTP, or parse failure so
    the caller (the poller) can keep the previous snapshot. This never runs on
    the proxy request path.
    """
    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    # A single attempt; the ~60s poll cadence is the retry.
    retry_options = ExponentialRetry(attempts=1)
    try:
        async with lease_retry_client(client) as retry_client:
            async with retry_client.request(
                "GET",
                url,
                timeout=timeout,
                retry_options=retry_options,
            ) as resp:
                if resp.status >= 400:
                    raise OpenAIStatusFetchError(
                        f"OpenAI status fetch failed ({resp.status})",
                        status_code=resp.status,
                    )
                data = await _safe_json(resp)
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        logger.debug("OpenAI status fetch transport error request_id=%s error=%s", get_request_id(), exc)
        raise OpenAIStatusFetchError(f"OpenAI status fetch failed: {exc}") from exc

    try:
        return parse_openai_status_summary(data)
    except ValidationError as exc:
        raise OpenAIStatusFetchError("OpenAI status payload was not the expected shape") from exc


async def _safe_json(resp: aiohttp.ClientResponse) -> JsonObject:
    try:
        data = await resp.json(content_type=None)
    except Exception as exc:  # noqa: BLE001 - any decode failure is a graceful fetch failure
        raise OpenAIStatusFetchError("OpenAI status payload was not valid JSON") from exc
    if not isinstance(data, dict):
        raise OpenAIStatusFetchError("OpenAI status payload was not a JSON object")
    return data
