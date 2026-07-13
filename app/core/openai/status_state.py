from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.core.utils.time import utcnow

# Public status page shown to operators / clients.
OPENAI_STATUS_PAGE_URL = "https://status.openai.com"

# A stored snapshot older than this is treated as stale. The poller runs every
# ~60s, so this tolerates a few missed polls before the dashboard/annotations
# stop trusting the cached data.
OPENAI_STATUS_STALE_AFTER_SECONDS = 180.0

# Statuspage overall-indicator values, ascending severity. "none" == all clear.
STATUS_INDICATOR_NONE = "none"
_DEGRADED_INDICATORS = frozenset({"minor", "major", "critical"})

# Statuspage component statuses that count as healthy. Anything else
# (degraded_performance, partial_outage, major_outage) is a degradation.
_OPERATIONAL_COMPONENT_STATUSES = frozenset({"operational", "under_maintenance"})

# A component is relevant to the Responses/Codex API path when its name mentions
# "api" (covers "API", "Responses API", "Realtime API", ...). ChatGPT-web-only
# components (e.g. "ChatGPT") do not match and are intentionally ignored so a
# consumer-web-only incident never gets attributed to the proxy's upstream.
_API_COMPONENT_KEYWORD = "api"

_IMPACT_RANK = {"none": 0, "minor": 1, "major": 2, "critical": 3}


def _mentions_api(name: str) -> bool:
    return _API_COMPONENT_KEYWORD in name.lower()


@dataclass(frozen=True, slots=True)
class OpenAIStatusComponent:
    id: str
    name: str
    status: str

    @property
    def operational(self) -> bool:
        return self.status in _OPERATIONAL_COMPONENT_STATUSES

    @property
    def api_relevant(self) -> bool:
        return _mentions_api(self.name)


@dataclass(frozen=True, slots=True)
class OpenAIStatusIncident:
    id: str
    name: str
    impact: str
    status: str
    started_at: datetime | None
    shortlink: str | None
    component_names: tuple[str, ...]

    @property
    def affects_api(self) -> bool:
        return any(_mentions_api(name) for name in self.component_names)


@dataclass(frozen=True, slots=True)
class OpenAIStatusSnapshot:
    indicator: str
    description: str
    components: tuple[OpenAIStatusComponent, ...]
    incidents: tuple[OpenAIStatusIncident, ...]
    fetched_at: datetime

    @property
    def degraded(self) -> bool:
        return self.indicator in _DEGRADED_INDICATORS

    def api_incident(self) -> OpenAIStatusIncident | None:
        """Return the highest-impact unresolved incident affecting an API component."""
        candidates = [incident for incident in self.incidents if incident.affects_api]
        if not candidates:
            return None
        return max(candidates, key=lambda incident: _IMPACT_RANK.get(incident.impact, 0))

    def degraded_api_component(self) -> OpenAIStatusComponent | None:
        for component in self.components:
            if component.api_relevant and not component.operational:
                return component
        return None


@dataclass(frozen=True, slots=True)
class OpenAIStatusState:
    snapshot: OpenAIStatusSnapshot | None
    updated_at: datetime | None
    stale: bool


class OpenAIStatusStore:
    """Process-local, thread-safe holder for the latest OpenAI status snapshot.

    Writes come from the async poller; reads come from both the async endpoint
    handler and the synchronous error-envelope builder (``openai_error``). A
    plain ``threading.Lock`` guarding immutable-reference swaps keeps reads
    non-blocking for both callers without requiring an event loop.
    """

    def __init__(self, *, stale_after_seconds: float = OPENAI_STATUS_STALE_AFTER_SECONDS) -> None:
        self._stale_after = timedelta(seconds=stale_after_seconds)
        self._snapshot: OpenAIStatusSnapshot | None = None
        self._updated_at: datetime | None = None
        self._lock = threading.Lock()

    def record_success(self, snapshot: OpenAIStatusSnapshot) -> None:
        with self._lock:
            self._snapshot = snapshot
            self._updated_at = snapshot.fetched_at

    def record_failure(self) -> None:
        """Keep the previous snapshot; staleness is derived from age on read."""
        return None

    def clear(self) -> None:
        with self._lock:
            self._snapshot = None
            self._updated_at = None

    def get_state(self, *, now: datetime | None = None) -> OpenAIStatusState:
        with self._lock:
            snapshot = self._snapshot
            updated_at = self._updated_at
        reference = now or utcnow()
        stale = snapshot is None or updated_at is None or (reference - updated_at) > self._stale_after
        return OpenAIStatusState(snapshot=snapshot, updated_at=updated_at, stale=stale)


_store: OpenAIStatusStore | None = None


def get_openai_status_store() -> OpenAIStatusStore:
    global _store
    if _store is None:
        _store = OpenAIStatusStore()
    return _store
