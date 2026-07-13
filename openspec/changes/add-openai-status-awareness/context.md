# Context: add-openai-status-awareness

## Purpose

Give operators an instant, server-sourced signal of whether a failure is OpenAI's
platform or the proxy. One poller is the single source of truth; the dashboard
banner and the downstream error annotation both read the same cached snapshot.

## Key decisions

- **Single funnel for error enrichment.** The original design pointed at
  `app/modules/proxy/_service/support.py::_stream_settlement_error_payload` as the
  downstream seam. Investigation showed that helper feeds only load-balancer
  account-health writes (`_handle_stream_error`) and never reaches the client. The
  actual single funnel for every client-visible error message — non-stream
  envelopes and streaming `response.failed` events alike — is
  `app/core/errors.py::openai_error` (streaming's `response_failed_event` delegates
  to it). The advisory annotation is applied there, strictly gated so it is a
  no-op for anything that is not an upstream-attributable failure during an active
  API incident. This covers both transports without editing ~80 call sites.

- **Advisory allowlist, not the routing classifier.** Gating reuses the intent of
  `app.modules.proxy.helpers.classify_upstream_failure` (retryable_transient + 5xx)
  but keeps an independent allowlist in the core layer
  (`app/core/openai/status_annotation.py`). Enrichment is a presentation concern,
  not a routing decision, and core must not depend on the proxy module.

- **Per-process poller, not leader-gated.** The snapshot lives in per-process
  memory and every replica needs its own fresh copy for the endpoint and the
  sync `openai_error` read path. The poll is a single lightweight public GET, so
  running it on every replica is cheap; leader-gating would starve non-leaders.

- **Staleness is age-derived.** A failed poll keeps the previous snapshot and lets
  it age past the staleness threshold (default 180s ≈ three missed 60s polls),
  so a dead scheduler self-heals into "stale" without a separate failure flag.

- **API/Codex relevance, excluding ChatGPT.** A component/incident is relevant
  only when its name mentions "api" or "codex" but NOT "chatgpt" (the exclusion
  wins even when "codex" is present). So `Codex API`, `API`, `Responses API`,
  `Realtime API`, `Compliance API` are relevant; `Codex in ChatGPT Desktop`,
  `ChatGPT Work`, `Conversations`, `Sites`, `Agent`, `Batch`, `Embeddings` are
  ignored so a consumer-web outage is never attributed to the proxy's upstream.

- **Key on an API/Codex-scoped signal, not the overall rollup.** OpenAI's
  Statuspage `indicator` rolls up all surfaces, so a ChatGPT-web-only incident
  makes it `minor`/`major`. Both the banner and the error annotation instead key
  on `snapshot.api_degraded` (a relevant incident exists OR a relevant component
  is non-operational) with a separate `api_indicator` = worst of relevant
  incident impacts and component statuses. The endpoint exposes this as
  `apiAffected`/`apiIndicator`/`apiIncident`/`apiComponent`; the raw overall
  `indicator`/`description` remain in the payload as informational only. Component
  statuses map onto the severity scale as degraded_performance→minor,
  partial_outage→major, major_outage→critical.

## Failure modes

- status.openai.com unreachable/slow → `OpenAIStatusFetchError`, previous snapshot
  retained, endpoint/annotation degrade to stale (no annotation, banner hidden).
- Malformed payload → treated as a fetch failure (graceful).
- Store empty (before first poll) → endpoint returns indicator `unknown`, stale.

## Example

`"Upstream error: bad gateway"` →
`"Upstream error: bad gateway — OpenAI reports a major API incident: \"Elevated errors on the Responses API\" (status.openai.com)"`
only when the fresh snapshot shows an API-affecting `major` incident.
