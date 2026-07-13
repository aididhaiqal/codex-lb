"""Advisory enrichment of upstream error messages with OpenAI status context.

When codex-lb returns an upstream-attributable failure to a downstream client
and OpenAI's status page reports an API-affecting incident, the client-visible
error message is extended with a short note so the operator can instantly tell
the failure originated at OpenAI, not the proxy.

Rules (held firmly):
- Advisory only: this never fails a request, never changes routing/selection.
  It only extends the human-readable ``message`` of an error that already
  happened; the JSON envelope structure is left intact.
- Enriches only upstream-attributable failures (5xx, gateway/connection/timeout).
  Rate-limit/quota (429), auth (401/403), and client 4xx are never enriched.
- Component-aware: only annotates when the cached snapshot is fresh AND shows a
  degradation affecting an API/Responses-relevant component.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.core.openai.status_state import OpenAIStatusState, get_openai_status_store

if TYPE_CHECKING:
    from app.core.errors import OpenAIErrorEnvelope

logger = logging.getLogger(__name__)

# Host label appended to the note (matches the public status page).
_STATUS_PAGE_HOST = "status.openai.com"

# Advisory allowlist of upstream-attributable error codes. This mirrors the
# routing-side classification in ``app.modules.proxy.helpers.classify_upstream_failure``
# (retryable_transient + 5xx) but is kept as an independent allowlist because
# this is an advisory presentation concern, not a routing decision, and it lives
# in the core layer with no dependency on the proxy module.
_UPSTREAM_ATTRIBUTABLE_ERROR_CODES = frozenset(
    {
        "server_error",
        "upstream_error",
        "overloaded_error",
        "upstream_unavailable",
        "upstream_request_timeout",
        "stream_idle_timeout",
        "stream_incomplete",
        "bad_gateway",
        "gateway_timeout",
    }
)
_UPSTREAM_ATTRIBUTABLE_HTTP_STATUSES = frozenset({500, 502, 503, 504})
# Account/tenant-specific or client-caused statuses are never OpenAI outages.
_NON_ATTRIBUTABLE_HTTP_STATUSES = frozenset({400, 401, 403, 404, 409, 422, 429})

# Sentinel used to keep annotation idempotent across envelope round-trips.
_ANNOTATION_SENTINEL = "OpenAI reports "

_IMPACT_PHRASES = {
    "critical": "a critical API incident",
    "major": "a major API incident",
    "minor": "a minor API incident",
}


def is_upstream_attributable(*, error_code: str | None, http_status: int | None = None) -> bool:
    """Whether a failure should be treated as attributable to an OpenAI outage."""
    if http_status is not None:
        if http_status in _NON_ATTRIBUTABLE_HTTP_STATUSES:
            return False
        if http_status in _UPSTREAM_ATTRIBUTABLE_HTTP_STATUSES:
            return True
    if error_code is None:
        return False
    return error_code in _UPSTREAM_ATTRIBUTABLE_ERROR_CODES


def openai_status_api_note(state: OpenAIStatusState) -> str | None:
    """Return a concise API-incident note, or None if nothing should be shown."""
    if state.stale or state.snapshot is None:
        return None
    snapshot = state.snapshot
    if not snapshot.degraded:
        return None
    incident = snapshot.api_incident()
    if incident is not None:
        phrase = _IMPACT_PHRASES.get(incident.impact, "an API incident")
        return f'{_ANNOTATION_SENTINEL}{phrase}: "{incident.name}" ({_STATUS_PAGE_HOST})'
    component = snapshot.degraded_api_component()
    if component is not None:
        return f'{_ANNOTATION_SENTINEL}degraded API service: "{component.name}" ({_STATUS_PAGE_HOST})'
    return None


def annotate_upstream_error_message(
    message: str,
    *,
    error_code: str | None,
    error_type: str | None = None,
    http_status: int | None = None,
) -> str:
    """Return ``message`` extended with an OpenAI-status note when warranted.

    Never raises: on any unexpected error the original message is returned
    unchanged so this can be called safely from the hot error-envelope path.
    """
    try:
        if not message or _ANNOTATION_SENTINEL in message:
            return message
        if not is_upstream_attributable(error_code=error_code, http_status=http_status):
            return message
        note = openai_status_api_note(get_openai_status_store().get_state())
        if note is None:
            return message
        return f"{message} — {note}"
    except Exception:  # noqa: BLE001 - annotation must never break error delivery
        logger.debug("OpenAI status annotation skipped", exc_info=True)
        return message


def maybe_annotate_upstream_error(
    envelope: OpenAIErrorEnvelope,
    *,
    error_code: str | None = None,
    http_status: int | None = None,
) -> OpenAIErrorEnvelope:
    """Annotate an OpenAI error envelope in place (idempotent, advisory-only)."""
    try:
        error = envelope.get("error")
        if not isinstance(error, dict):
            return envelope
        message = error.get("message")
        if not isinstance(message, str):
            return envelope
        code = error_code
        if code is None and isinstance(error.get("code"), str):
            code = error["code"]
        error_type = error["type"] if isinstance(error.get("type"), str) else None
        error["message"] = annotate_upstream_error_message(
            message,
            error_code=code,
            error_type=error_type,
            http_status=http_status,
        )
        return envelope
    except Exception:  # noqa: BLE001 - annotation must never break error delivery
        logger.debug("OpenAI status envelope annotation skipped", exc_info=True)
        return envelope
