from __future__ import annotations

from app.core.openai.status_state import OpenAIStatusState, get_openai_status_store
from app.modules.system_status.schemas import (
    SystemStatusComponentResponse,
    SystemStatusIncidentResponse,
    SystemStatusResponse,
)

# Indicator returned before the poller has fetched any snapshot.
UNKNOWN_INDICATOR = "unknown"


def get_system_status() -> SystemStatusResponse:
    return _to_response(get_openai_status_store().get_state())


def _to_response(state: OpenAIStatusState) -> SystemStatusResponse:
    snapshot = state.snapshot
    if snapshot is None:
        return SystemStatusResponse(
            indicator=UNKNOWN_INDICATOR,
            description="",
            components=[],
            incidents=[],
            updated_at=state.updated_at,
            stale=state.stale,
        )
    return SystemStatusResponse(
        indicator=snapshot.indicator,
        description=snapshot.description,
        components=[
            SystemStatusComponentResponse(name=component.name, status=component.status)
            for component in snapshot.components
        ],
        incidents=[
            SystemStatusIncidentResponse(
                name=incident.name,
                impact=incident.impact,
                status=incident.status,
                started_at=incident.started_at,
                shortlink=incident.shortlink,
                affected_components=list(incident.component_names),
            )
            for incident in snapshot.incidents
        ],
        updated_at=state.updated_at,
        stale=state.stale,
    )
