from __future__ import annotations

from app.core.openai.status_state import (
    OpenAIStatusIncident,
    OpenAIStatusState,
    get_openai_status_store,
)
from app.modules.system_status.schemas import (
    SystemStatusComponentResponse,
    SystemStatusIncidentResponse,
    SystemStatusResponse,
)

# Indicator returned before the poller has fetched any snapshot.
UNKNOWN_INDICATOR = "unknown"


def get_system_status() -> SystemStatusResponse:
    return _to_response(get_openai_status_store().get_state())


def _incident_response(incident: OpenAIStatusIncident) -> SystemStatusIncidentResponse:
    return SystemStatusIncidentResponse(
        name=incident.name,
        impact=incident.impact,
        status=incident.status,
        started_at=incident.started_at,
        shortlink=incident.shortlink,
        affected_components=list(incident.component_names),
    )


def _to_response(state: OpenAIStatusState) -> SystemStatusResponse:
    snapshot = state.snapshot
    if snapshot is None:
        return SystemStatusResponse(
            indicator=UNKNOWN_INDICATOR,
            description="",
            api_affected=False,
            api_indicator=UNKNOWN_INDICATOR,
            api_incident=None,
            api_component=None,
            components=[],
            incidents=[],
            updated_at=state.updated_at,
            stale=state.stale,
        )
    api_incident = snapshot.api_incident()
    api_component = snapshot.degraded_api_component()
    return SystemStatusResponse(
        indicator=snapshot.indicator,
        description=snapshot.description,
        api_affected=snapshot.api_degraded,
        api_indicator=snapshot.api_indicator,
        api_incident=_incident_response(api_incident) if api_incident is not None else None,
        api_component=(
            SystemStatusComponentResponse(name=api_component.name, status=api_component.status)
            if api_component is not None
            else None
        ),
        components=[
            SystemStatusComponentResponse(name=component.name, status=component.status)
            for component in snapshot.components
        ],
        incidents=[_incident_response(incident) for incident in snapshot.incidents],
        updated_at=state.updated_at,
        stale=state.stale,
    )
