from __future__ import annotations

from datetime import timedelta

from app.core.errors import OpenAIErrorEnvelope, openai_error, response_failed_event
from app.core.openai.status_annotation import (
    annotate_upstream_error_message,
    is_upstream_attributable,
    maybe_annotate_upstream_error,
)
from app.core.openai.status_state import (
    OpenAIStatusComponent,
    OpenAIStatusIncident,
    OpenAIStatusSnapshot,
    get_openai_status_store,
)
from app.core.utils.time import utcnow

_API_COMPONENT = OpenAIStatusComponent(id="c_api", name="API", status="major_outage")
_CHATGPT_COMPONENT = OpenAIStatusComponent(id="c_chat", name="ChatGPT", status="major_outage")
_API_INCIDENT = OpenAIStatusIncident(
    id="i1",
    name="Elevated errors on the Responses API",
    impact="major",
    status="investigating",
    started_at=None,
    shortlink="https://stspg.io/x",
    component_names=("API",),
)
_CHATGPT_INCIDENT = OpenAIStatusIncident(
    id="i2",
    name="ChatGPT web is slow",
    impact="major",
    status="investigating",
    started_at=None,
    shortlink="https://stspg.io/y",
    component_names=("ChatGPT",),
)


def _seed(
    *,
    indicator: str,
    components: tuple[OpenAIStatusComponent, ...] = (),
    incidents: tuple[OpenAIStatusIncident, ...] = (),
    age_seconds: float = 0.0,
) -> None:
    snapshot = OpenAIStatusSnapshot(
        indicator=indicator,
        description="",
        components=components,
        incidents=incidents,
        fetched_at=utcnow() - timedelta(seconds=age_seconds),
    )
    get_openai_status_store().record_success(snapshot)


def test_enriches_upstream_error_during_api_incident() -> None:
    _seed(indicator="major", components=(_API_COMPONENT,), incidents=(_API_INCIDENT,))
    message = openai_error("upstream_error", "Upstream error: bad gateway")["error"]["message"]
    assert message == (
        "Upstream error: bad gateway — OpenAI reports a major API incident: "
        '"Elevated errors on the Responses API" (status.openai.com)'
    )


def test_enrichment_reaches_streaming_response_failed_event() -> None:
    _seed(indicator="major", components=(_API_COMPONENT,), incidents=(_API_INCIDENT,))
    event = response_failed_event("server_error", "Upstream error")
    assert "OpenAI reports a major API incident" in event["response"]["error"]["message"]


def test_enriches_component_only_degradation() -> None:
    _seed(indicator="minor", components=(OpenAIStatusComponent(id="c_api", name="API", status="degraded_performance"),))
    message = openai_error("upstream_unavailable", "Upstream error")["error"]["message"]
    assert 'OpenAI reports degraded API service: "API" (status.openai.com)' in message


def test_does_not_enrich_rate_limit() -> None:
    _seed(indicator="major", components=(_API_COMPONENT,), incidents=(_API_INCIDENT,))
    assert openai_error("rate_limit_exceeded", "Rate limited")["error"]["message"] == "Rate limited"


def test_does_not_enrich_quota() -> None:
    _seed(indicator="major", components=(_API_COMPONENT,), incidents=(_API_INCIDENT,))
    assert openai_error("insufficient_quota", "No quota")["error"]["message"] == "No quota"


def test_does_not_enrich_client_4xx() -> None:
    _seed(indicator="major", components=(_API_COMPONENT,), incidents=(_API_INCIDENT,))
    assert openai_error("invalid_request_error", "Bad request")["error"]["message"] == "Bad request"


def test_does_not_enrich_auth_http_status() -> None:
    # A 401/403 upstream is auth, never an outage, even with an otherwise
    # attributable error_code — the explicit status wins.
    _seed(indicator="major", components=(_API_COMPONENT,), incidents=(_API_INCIDENT,))
    envelope: OpenAIErrorEnvelope = {"error": {"message": "boom", "type": "server_error", "code": "server_error"}}
    result = maybe_annotate_upstream_error(envelope, error_code="server_error", http_status=401)
    assert result["error"]["message"] == "boom"


def test_does_not_enrich_when_status_clear() -> None:
    _seed(indicator="none", components=(), incidents=())
    assert openai_error("upstream_error", "Upstream error")["error"]["message"] == "Upstream error"


def test_does_not_enrich_when_snapshot_stale() -> None:
    _seed(indicator="major", components=(_API_COMPONENT,), incidents=(_API_INCIDENT,), age_seconds=100_000)
    assert openai_error("upstream_error", "Upstream error")["error"]["message"] == "Upstream error"


def test_does_not_enrich_when_no_snapshot() -> None:
    get_openai_status_store().clear()
    assert openai_error("upstream_error", "Upstream error")["error"]["message"] == "Upstream error"


def test_does_not_enrich_chatgpt_only_incident() -> None:
    _seed(indicator="major", components=(_CHATGPT_COMPONENT,), incidents=(_CHATGPT_INCIDENT,))
    assert openai_error("upstream_error", "Upstream error")["error"]["message"] == "Upstream error"


def test_annotation_is_idempotent() -> None:
    _seed(indicator="major", components=(_API_COMPONENT,), incidents=(_API_INCIDENT,))
    once = annotate_upstream_error_message("Upstream error", error_code="upstream_error")
    twice = annotate_upstream_error_message(once, error_code="upstream_error")
    assert once == twice
    assert once.count("OpenAI reports") == 1


def test_is_upstream_attributable_matrix() -> None:
    assert is_upstream_attributable(error_code="server_error") is True
    assert is_upstream_attributable(error_code="upstream_unavailable") is True
    assert is_upstream_attributable(error_code=None, http_status=502) is True
    assert is_upstream_attributable(error_code=None, http_status=500) is True
    assert is_upstream_attributable(error_code="server_error", http_status=429) is False
    assert is_upstream_attributable(error_code="rate_limit_exceeded") is False
    assert is_upstream_attributable(error_code="insufficient_quota") is False
    assert is_upstream_attributable(error_code="invalid_request_error") is False
    assert is_upstream_attributable(error_code=None) is False
