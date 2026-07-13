from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from app.core.clients.openai_status import (
    OpenAIStatusFetchError,
    fetch_openai_status,
    parse_openai_status_summary,
)
from app.core.types import JsonObject

SAMPLE_SUMMARY: JsonObject = {
    "page": {"id": "abc", "name": "OpenAI"},
    "status": {"indicator": "major", "description": "Partial Outage"},
    "components": [
        {"id": "c_api", "name": "API", "status": "major_outage"},
        {"id": "c_rt", "name": "Realtime API", "status": "degraded_performance"},
        {"id": "c_chat", "name": "ChatGPT", "status": "operational"},
        {"id": "c_blank", "name": "", "status": "operational"},
    ],
    "incidents": [
        {
            "id": "inc_1",
            "name": "Elevated errors on the Responses API",
            "impact": "major",
            "status": "investigating",
            "started_at": "2026-07-13T10:00:00.000Z",
            "shortlink": "https://stspg.io/abc",
            "components": [{"id": "c_api", "name": "API"}],
        },
        {
            "id": "inc_resolved",
            "name": "Old ChatGPT hiccup",
            "impact": "minor",
            "status": "resolved",
            "started_at": "2026-07-12T10:00:00.000Z",
            "shortlink": "https://stspg.io/old",
            "components": [{"id": "c_chat", "name": "ChatGPT"}],
        },
    ],
}


def test_parse_extracts_indicator_components_and_unresolved_incidents() -> None:
    fetched_at = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
    snapshot = parse_openai_status_summary(SAMPLE_SUMMARY, fetched_at=fetched_at)

    assert snapshot.indicator == "major"
    assert snapshot.description == "Partial Outage"
    assert snapshot.degraded is True
    assert snapshot.fetched_at == fetched_at

    # Blank-named components are dropped; the rest are preserved with status.
    names = [component.name for component in snapshot.components]
    assert names == ["API", "Realtime API", "ChatGPT"]
    api_component = next(component for component in snapshot.components if component.name == "API")
    assert api_component.api_relevant is True
    assert api_component.operational is False
    chatgpt = next(component for component in snapshot.components if component.name == "ChatGPT")
    assert chatgpt.api_relevant is False

    # Only the unresolved incident survives.
    assert len(snapshot.incidents) == 1
    incident = snapshot.incidents[0]
    assert incident.name == "Elevated errors on the Responses API"
    assert incident.impact == "major"
    assert incident.status == "investigating"
    assert incident.shortlink == "https://stspg.io/abc"
    assert incident.component_names == ("API",)
    assert incident.affects_api is True

    assert snapshot.api_incident() is incident


def test_parse_all_clear_summary() -> None:
    snapshot = parse_openai_status_summary({"status": {"indicator": "none", "description": "All Systems Operational"}})
    assert snapshot.indicator == "none"
    assert snapshot.degraded is False
    assert snapshot.components == ()
    assert snapshot.incidents == ()
    assert snapshot.api_incident() is None


def _response(*, status: int = 200, json_data: object = None) -> MagicMock:
    response = MagicMock()
    response.status = status
    response.json = AsyncMock(return_value=json_data)
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock(return_value=False)
    return response


def _retry_client(response: MagicMock) -> MagicMock:
    client = MagicMock()
    client.request = MagicMock(return_value=response)
    return client


async def test_fetch_openai_status_returns_snapshot() -> None:
    client = _retry_client(_response(json_data=SAMPLE_SUMMARY))
    snapshot = await fetch_openai_status(client=client)
    assert snapshot.indicator == "major"
    assert snapshot.api_incident() is not None


async def test_fetch_openai_status_raises_on_http_error() -> None:
    client = _retry_client(_response(status=503, json_data={}))
    with pytest.raises(OpenAIStatusFetchError) as exc_info:
        await fetch_openai_status(client=client)
    assert exc_info.value.status_code == 503


async def test_fetch_openai_status_raises_on_transport_error() -> None:
    client = MagicMock()
    client.request = MagicMock(side_effect=aiohttp.ClientError("connection reset"))
    with pytest.raises(OpenAIStatusFetchError):
        await fetch_openai_status(client=client)
