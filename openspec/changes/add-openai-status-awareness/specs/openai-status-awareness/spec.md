# openai-status-awareness Specification

## ADDED Requirements

### Requirement: OpenAI status is polled server-side and cached with staleness

The service MUST poll `https://status.openai.com/api/v2/summary.json` on a background schedule (default every ~60s, configurable via `openai_status_refresh_interval_seconds`, enabled by default and disableable via `openai_status_enabled`) and hold the latest snapshot — overall indicator, components, and unresolved incidents — in a process-local, concurrency-safe holder with a last-updated timestamp. A snapshot older than the staleness threshold MUST be reported as stale. The poll MUST fail gracefully: any transport, HTTP, timeout, or parse error MUST retain the previous snapshot and MUST NOT raise into any request-handling path. The status page MUST NOT be fetched on the proxy request path.

#### Scenario: Successful poll refreshes the snapshot

- **WHEN** the poller receives a valid `summary.json` with indicator `major` and an unresolved incident
- **THEN** the cached snapshot exposes indicator `major`, the reported components, and the unresolved incident
- **AND** the snapshot is reported as not stale immediately after the refresh

#### Scenario: Failed poll keeps the previous snapshot

- **GIVEN** a previously cached snapshot
- **WHEN** a later poll fails with a transport or HTTP error
- **THEN** the cached snapshot is unchanged and no error propagates out of the poller

#### Scenario: Resolved incidents are not retained

- **WHEN** the summary lists an incident whose status is `resolved` or `postmortem`
- **THEN** that incident MUST NOT appear in the cached snapshot's unresolved incidents

### Requirement: Relevance is scoped to API/Codex surfaces, excluding ChatGPT

The service MUST treat a status component or incident as relevant to codex-lb only when its name (case-insensitive) contains "api" or "codex" AND does NOT contain "chatgpt"; the "chatgpt" exclusion MUST win even when "codex" is also present. Names such as `API`, `Codex API`, `Responses API`, `Realtime API`, and `Compliance API` are relevant; `Codex in ChatGPT Desktop`, `ChatGPT Work`, `Conversations`, `Sites`, `Agent`, `Batch`, and `Embeddings` are NOT relevant.

The service MUST compute an API/Codex-scoped degradation signal that is independent of OpenAI's overall Statuspage rollup: it is degraded when a relevant unresolved incident exists OR a relevant component is non-operational, and its severity indicator is the worst of the relevant incident impacts and relevant component statuses (else `none`).

#### Scenario: API and Codex names are relevant, ChatGPT names are not

- **WHEN** a component is named `Codex API`, `API`, or `Responses API`
- **THEN** it is treated as relevant to codex-lb
- **AND** a component named `Codex in ChatGPT Desktop`, `Conversations`, `Sites`, or `Agent` is NOT treated as relevant

#### Scenario: API-scoped signal ignores the overall rollup

- **GIVEN** a snapshot whose overall indicator is degraded but whose only degraded surface is ChatGPT-web
- **WHEN** the API/Codex-scoped signal is computed
- **THEN** it MUST report not degraded with indicator `none`

### Requirement: System status endpoint returns the cached snapshot

The service MUST expose `GET /api/system-status` returning the cached snapshot as `indicator`, `description`, `apiAffected`, `apiIndicator`, `apiIncident`, `apiComponent`, `components`, `incidents`, `updatedAt`, `stale`, and `statusPageUrl`. The `indicator`/`description` fields carry OpenAI's overall rollup and are informational; the `api*` fields carry the API/Codex-scoped signal and are what consumers key on. The endpoint MUST serve from the in-memory cache and MUST NOT fetch the status page per request. When no snapshot has been fetched yet, the endpoint MUST return `indicator` `unknown`, `apiAffected` false, `stale` true, and empty component/incident lists.

#### Scenario: Endpoint returns an API-affected snapshot

- **GIVEN** a cached snapshot with a Codex/API incident and a degraded Codex/API component
- **WHEN** a dashboard client GETs `/api/system-status`
- **THEN** `apiAffected` is true, `apiIndicator` reflects the worst relevant severity, and `apiIncident`/`apiComponent` name the relevant incident and component

#### Scenario: Endpoint reports API-clear when only ChatGPT-web is degraded

- **GIVEN** a cached snapshot whose overall indicator is `minor` but whose only degraded component is ChatGPT-web (e.g. `Conversations`)
- **WHEN** a dashboard client GETs `/api/system-status`
- **THEN** `indicator` is `minor` but `apiAffected` is false and `apiIndicator` is `none`

#### Scenario: Endpoint before the first successful poll

- **GIVEN** no snapshot has been cached
- **WHEN** a dashboard client GETs `/api/system-status`
- **THEN** `indicator` is `unknown`, `apiAffected` is false, `stale` is true, and `components`/`incidents` are empty

### Requirement: Upstream-attributable errors are advisorily annotated during API/Codex incidents

When the service returns an upstream-attributable failure (upstream 5xx, gateway/bad-gateway, connection error, or timeout) to a downstream client AND the cached snapshot is fresh AND the API/Codex-scoped signal is degraded, the client-visible error `message` MUST be extended with a concise note identifying OpenAI's status page as the source. Gating MUST key on the API/Codex-scoped signal, NOT on OpenAI's overall rollup. The annotation MUST be advisory only: it MUST NOT fail a request that would otherwise succeed, MUST NOT change routing or account selection, and MUST leave the JSON error-envelope structure intact (extending only the human-readable `message`). Annotation MUST be idempotent.

The service MUST NOT annotate failures that are not OpenAI outages: rate-limit or quota failures (including HTTP 429), authentication failures (HTTP 401/403), or client 4xx errors. The service MUST NOT annotate when the API/Codex-scoped signal is clear, when the snapshot is stale or absent, or when the only degradation is a ChatGPT-web surface.

#### Scenario: Gateway error during a Codex/API incident is annotated

- **GIVEN** a fresh snapshot whose API/Codex-scoped signal is degraded by a `Codex API` incident
- **WHEN** the proxy returns a bad-gateway upstream error to the client
- **THEN** the client-visible message is extended with a note naming the OpenAI API incident and `status.openai.com`
- **AND** the error code, type, and envelope structure are unchanged

#### Scenario: Rate-limit and auth failures are never annotated

- **GIVEN** a fresh snapshot whose API/Codex-scoped signal is degraded
- **WHEN** the proxy returns a rate-limit (429), quota, or auth (401/403) error
- **THEN** the client-visible message is returned unchanged

#### Scenario: No annotation when the API/Codex signal is clear or stale

- **GIVEN** the API/Codex-scoped signal is clear, or the snapshot is stale or absent
- **WHEN** the proxy returns an upstream 5xx error
- **THEN** the client-visible message is returned unchanged

#### Scenario: ChatGPT-web-only degradation does not annotate upstream errors

- **GIVEN** a fresh snapshot whose overall rollup is degraded but whose only degradation is a ChatGPT-web surface (e.g. `Conversations`, or `Codex in ChatGPT Desktop`)
- **WHEN** the proxy returns an upstream 5xx error
- **THEN** the client-visible message is returned unchanged

### Requirement: Dashboard surfaces API/Codex status from the server snapshot

The dashboard MUST display OpenAI status by reading `GET /api/system-status` (not by fetching `status.openai.com` from the browser) and MUST key its presentation on the API/Codex-scoped signal (`apiAffected`/`apiIndicator`), not the overall rollup. When `apiAffected` is false the dashboard MUST show a compact operational indicator. When `apiAffected` is true the dashboard MUST show an alert banner containing the incident title, the affected API/Codex component, and a link to `status.openai.com`. When the snapshot is stale the dashboard MUST NOT assert a status.

#### Scenario: API-clear status shows a compact indicator

- **WHEN** `/api/system-status` reports `apiAffected` false and not stale
- **THEN** the dashboard shows a compact operational indicator and no alert banner

#### Scenario: ChatGPT-web-only degradation still shows the clear state

- **WHEN** `/api/system-status` reports overall `indicator` `minor` but `apiAffected` false and not stale
- **THEN** the dashboard shows the compact operational indicator and no alert banner

#### Scenario: API-affected status shows an incident banner

- **WHEN** `/api/system-status` reports `apiAffected` true with a Codex/API incident and not stale
- **THEN** the dashboard shows an alert banner with the incident title, affected component, and a `status.openai.com` link

#### Scenario: Stale status shows nothing

- **WHEN** `/api/system-status` reports `stale` true
- **THEN** the dashboard shows neither the indicator nor a banner
