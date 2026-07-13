from __future__ import annotations

from datetime import datetime

from app.core.openai.status_state import OPENAI_STATUS_PAGE_URL
from app.modules.shared.schemas import DashboardModel


class SystemStatusComponentResponse(DashboardModel):
    name: str
    status: str


class SystemStatusIncidentResponse(DashboardModel):
    name: str
    impact: str
    status: str
    started_at: datetime | None = None
    shortlink: str | None = None
    affected_components: list[str] = []


class SystemStatusResponse(DashboardModel):
    # ``indicator``/``description`` are the Statuspage overall rollup across all
    # OpenAI surfaces (none/minor/major/critical, or "unknown" before the first
    # poll) and are informational only. codex-lb keys presentation on the
    # ``api_*`` fields, which are scoped to API/Codex surfaces.
    indicator: str
    description: str
    # API/Codex-scoped signal (excludes ChatGPT-web surfaces).
    api_affected: bool
    api_indicator: str
    api_incident: SystemStatusIncidentResponse | None = None
    api_component: SystemStatusComponentResponse | None = None
    components: list[SystemStatusComponentResponse]
    incidents: list[SystemStatusIncidentResponse]
    updated_at: datetime | None
    stale: bool
    status_page_url: str = OPENAI_STATUS_PAGE_URL
