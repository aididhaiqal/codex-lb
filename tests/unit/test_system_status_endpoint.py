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
    assert body["components"] == []
    assert body["incidents"] == []
    assert body["statusPageUrl"] == "https://status.openai.com"


async def test_system_status_returns_cached_snapshot(async_client) -> None:
    snapshot = OpenAIStatusSnapshot(
        indicator="major",
        description="Partial Outage",
        components=(OpenAIStatusComponent(id="c_api", name="API", status="major_outage"),),
        incidents=(
            OpenAIStatusIncident(
                id="i1",
                name="Elevated errors on the Responses API",
                impact="major",
                status="investigating",
                started_at=None,
                shortlink="https://stspg.io/x",
                component_names=("API",),
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
    assert body["components"] == [{"name": "API", "status": "major_outage"}]
    assert len(body["incidents"]) == 1
    incident = body["incidents"][0]
    assert incident["name"] == "Elevated errors on the Responses API"
    assert incident["impact"] == "major"
    assert incident["affectedComponents"] == ["API"]
