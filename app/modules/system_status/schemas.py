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
    # ``indicator`` is the Statuspage overall indicator (none/minor/major/critical)
    # or "unknown" when the proxy has not fetched a snapshot yet.
    indicator: str
    description: str
    components: list[SystemStatusComponentResponse]
    incidents: list[SystemStatusIncidentResponse]
    updated_at: datetime | None
    stale: bool
    status_page_url: str = OPENAI_STATUS_PAGE_URL
