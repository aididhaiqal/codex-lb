from __future__ import annotations

from app.core.openai.status_state import (
    OpenAIStatusComponent,
    OpenAIStatusIncident,
    OpenAIStatusSnapshot,
    get_openai_status_store,
)
from app.core.utils.time import utcnow


async def test_system_status_returns_unknown_when_no_snapshot(async_client) -> None:
    get_openai_status_store().clear()
    resp = await async_client.get("/api/system-status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["indicator"] == "unknown"
    assert body["stale"] is True
    assert body["apiAffected"] is False
    assert body["apiIndicator"] == "unknown"
    assert body["apiIncident"] is None
    assert body["apiComponent"] is None
    assert body["components"] == []
    assert body["incidents"] == []
    assert body["statusPageUrl"] == "https://status.openai.com"


async def test_system_status_returns_cached_snapshot(async_client) -> None:
    snapshot = OpenAIStatusSnapshot(
        indicator="major",
        description="Partial Outage",
        components=(OpenAIStatusComponent(id="c_codex", name="Codex API", status="partial_outage"),),
        incidents=(
            OpenAIStatusIncident(
                id="i1",
                name="Elevated errors on the Responses API",
                impact="major",
                status="investigating",
                started_at=None,
                shortlink="https://stspg.io/x",
                component_names=("Codex API",),
            ),
        ),
        fetched_at=utcnow(),
    )
    get_openai_status_store().record_success(snapshot)

    resp = await async_client.get("/api/system-status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["indicator"] == "major"
    assert body["description"] == "Partial Outage"
    assert body["stale"] is False
    assert body["updatedAt"] is not None
    assert body["apiAffected"] is True
    # worst of {incident impact major, component partial_outage} -> major
    assert body["apiIndicator"] == "major"
    assert body["apiIncident"]["name"] == "Elevated errors on the Responses API"
    assert body["apiIncident"]["affectedComponents"] == ["Codex API"]
    assert body["apiComponent"] == {"name": "Codex API", "status": "partial_outage"}
    assert body["components"] == [{"name": "Codex API", "status": "partial_outage"}]
    assert len(body["incidents"]) == 1
    incident = body["incidents"][0]
    assert incident["name"] == "Elevated errors on the Responses API"
    assert incident["impact"] == "major"
    assert incident["affectedComponents"] == ["Codex API"]


async def test_system_status_chatgpt_only_is_not_api_affected(async_client) -> None:
    snapshot = OpenAIStatusSnapshot(
        indicator="minor",  # overall rollup is degraded
        description="Degraded Performance",
        components=(OpenAIStatusComponent(id="c_conv", name="Conversations", status="degraded_performance"),),
        incidents=(
            OpenAIStatusIncident(
                id="i1",
                name="ChatGPT web is slow",
                impact="minor",
                status="investigating",
                started_at=None,
                shortlink="https://stspg.io/y",
                component_names=("Conversations",),
            ),
        ),
        fetched_at=utcnow(),
    )
    get_openai_status_store().record_success(snapshot)

    resp = await async_client.get("/api/system-status")
    assert resp.status_code == 200
    body = resp.json()
    # Overall rollup is degraded but the API/Codex surface is clear.
    assert body["indicator"] == "minor"
    assert body["apiAffected"] is False
    assert body["apiIndicator"] == "none"
    assert body["apiIncident"] is None
    assert body["apiComponent"] is None
