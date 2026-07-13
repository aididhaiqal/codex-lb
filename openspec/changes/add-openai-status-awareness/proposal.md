## Why

When OpenAI has an incident, codex-lb surfaces the resulting upstream failures as generic proxy errors (`"Upstream error: bad gateway"`). Operators cannot tell from the dashboard or a downstream client's error whether the fault is OpenAI's platform or the proxy itself, so they waste time debugging codex-lb during an outage that is entirely upstream. OpenAI publishes a machine-readable status feed (`status.openai.com/api/v2/summary.json`); consuming it once, server-side, lets both the dashboard and downstream error messages point at the real cause.

## What Changes

- Add a leader-independent background poller that GETs the OpenAI status summary every ~60s (configurable, default-on) and holds the latest snapshot — overall indicator, components, and unresolved incidents — in a process-local, thread-safe state holder with a last-updated timestamp and a derived staleness flag. The poll fails gracefully: any transport/HTTP/parse error keeps the previous snapshot, which ages into staleness on its own. Nothing on the proxy request path ever fetches the status page.
- Scope relevance to **API/Codex** surfaces only: a component/incident matters when its name mentions "api" or "codex" but not "chatgpt". Both the banner and the annotation key on an **API/Codex-scoped signal** (`apiAffected`/`apiIndicator`) computed independently of OpenAI's overall Statuspage rollup, so a ChatGPT-web-only incident (e.g. `Conversations`, `Codex in ChatGPT Desktop`) never lights the banner or annotates proxy errors.
- Add `GET /api/system-status` (dashboard-session gated) returning the cached snapshot — the overall `indicator`/`description` (informational) plus the `apiAffected`/`apiIndicator`/`apiIncident`/`apiComponent` API-scoped signal — and a dashboard header widget that reads it: a small status dot when the API/Codex surface is clear, and an alert banner (incident title + affected component + link to `status.openai.com`) when `apiAffected`. The browser no longer fetches `status.openai.com` directly.
- Enrich downstream error messages: when codex-lb returns an **upstream-attributable** failure (5xx, gateway/connection/timeout) and the cached snapshot is fresh and the API/Codex-scoped signal is degraded, append a concise note to the client-visible message (e.g. `… — OpenAI reports a major API incident: "Elevated errors on the Responses API" (status.openai.com)`). This is advisory only: it never fails a request that would otherwise succeed, never changes routing/selection, only extends the human-readable message of an error that already happened, and never annotates rate-limit/quota (429), auth (401/403), client 4xx, or ChatGPT-web-only degradations.

## Capabilities

### New Capabilities

- `openai-status-awareness`: the status poller and its graceful-failure/staleness contract, the `GET /api/system-status` response contract, the advisory error-enrichment gating rules, and the dashboard presentation contract.

## Impact

- **Code**: new `app/core/clients/openai_status.py` (outbound client + parser), `app/core/openai/status_state.py` (snapshot holder), `app/core/openai/status_scheduler.py` (poller), `app/core/openai/status_annotation.py` (advisory enrichment); a one-line hook in `app/core/errors.py::openai_error` (the single funnel for client-visible error messages); a new `app/modules/system_status/` endpoint module; `app/main.py` lifespan + router wiring; three `openai_status_*` settings; a `frontend/src/features/system-status/` widget wired into the dashboard header.
- **Schema**: none (no migration; snapshot is in-memory only).
- **Ops**: one new periodic job (~60s), per-process, disabled via `openai_status_enabled=false`. One lightweight public GET per replica per interval.
- **Compatibility**: additive. The error envelope structure is unchanged — only the human-readable `message` string is extended, and only for upstream-attributable failures during a confirmed API incident.
