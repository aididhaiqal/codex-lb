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
_CODEX_API_COMPONENT = OpenAIStatusComponent(id="c_codex", name="Codex API", status="major_outage")
_CODEX_API_INCIDENT = OpenAIStatusIncident(
    id="i3",
    name="Codex API degraded",
    impact="major",
    status="investigating",
    started_at=None,
    shortlink="https://stspg.io/z",
    component_names=("Codex API",),
)
_CONVERSATIONS_COMPONENT = OpenAIStatusComponent(id="c_conv", name="Conversations", status="degraded_performance")


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


def test_enriches_codex_api_incident() -> None:
    _seed(indicator="major", components=(_CODEX_API_COMPONENT,), incidents=(_CODEX_API_INCIDENT,))
    message = openai_error("server_error", "Upstream error: bad gateway")["error"]["message"]
    assert 'OpenAI reports a major API incident: "Codex API degraded" (status.openai.com)' in message


def test_does_not_enrich_chatgpt_only_incident() -> None:
    _seed(indicator="major", components=(_CHATGPT_COMPONENT,), incidents=(_CHATGPT_INCIDENT,))
    assert openai_error("upstream_error", "Upstream error")["error"]["message"] == "Upstream error"


def test_does_not_enrich_conversations_only_incident() -> None:
    # Overall rollup is degraded (minor), but only ChatGPT-web "Conversations"
    # is affected — codex-lb's upstream is unaffected, so no annotation.
    _seed(indicator="minor", components=(_CONVERSATIONS_COMPONENT,))
    assert openai_error("upstream_error", "Upstream error")["error"]["message"] == "Upstream error"


def test_does_not_enrich_codex_in_chatgpt_desktop() -> None:
    # "Codex in ChatGPT Desktop" mentions "codex" but the "chatgpt" exclusion wins.
    component = OpenAIStatusComponent(id="c_desk", name="Codex in ChatGPT Desktop", status="major_outage")
    _seed(indicator="major", components=(component,))
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


def test_relevance_rule_matches_api_and_codex_but_not_chatgpt() -> None:
    relevant = ["API", "Codex API", "Responses API", "Realtime API", "Compliance API"]
    ignored = [
        "ChatGPT",
        "ChatGPT Work",
        "Codex in ChatGPT Desktop",
        "Conversations",
        "Sites",
        "Agent",
        "Batch",
        "Embeddings",
    ]
    for name in relevant:
        component = OpenAIStatusComponent(id="c", name=name, status="major_outage")
        assert component.api_or_codex_relevant is True, name
        incident = OpenAIStatusIncident(
            id="i",
            name=f"{name} incident",
            impact="major",
            status="investigating",
            started_at=None,
            shortlink=None,
            component_names=(name,),
        )
        assert incident.affects_api_or_codex is True, name
    for name in ignored:
        component = OpenAIStatusComponent(id="c", name=name, status="major_outage")
        assert component.api_or_codex_relevant is False, name


def test_api_indicator_reflects_worst_relevant_severity() -> None:
    # A ChatGPT major_outage is ignored; the relevant Codex API major_outage
    # escalates the API-scoped indicator to critical.
    snapshot = OpenAIStatusSnapshot(
        indicator="critical",  # overall rollup (informational)
        description="",
        components=(
            OpenAIStatusComponent(id="c1", name="ChatGPT", status="major_outage"),
            OpenAIStatusComponent(id="c2", name="Codex API", status="major_outage"),
        ),
        incidents=(),
        fetched_at=utcnow(),
    )
    assert snapshot.api_degraded is True
    assert snapshot.api_indicator == "critical"
    degraded = snapshot.degraded_api_component()
    assert degraded is not None
    assert degraded.name == "Codex API"


def test_api_degraded_false_for_chatgpt_only() -> None:
    snapshot = OpenAIStatusSnapshot(
        indicator="minor",
        description="",
        components=(_CONVERSATIONS_COMPONENT,),
        incidents=(_CHATGPT_INCIDENT,),
        fetched_at=utcnow(),
    )
    assert snapshot.api_degraded is False
    assert snapshot.api_indicator == "none"
    assert snapshot.api_incident() is None
