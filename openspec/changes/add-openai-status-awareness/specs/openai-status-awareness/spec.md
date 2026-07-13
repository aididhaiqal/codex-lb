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

### Requirement: System status endpoint returns the cached snapshot

The service MUST expose `GET /api/system-status` returning the cached snapshot as `indicator`, `description`, `components`, `incidents`, `updatedAt`, `stale`, and `statusPageUrl`. The endpoint MUST serve from the in-memory cache and MUST NOT fetch the status page per request. When no snapshot has been fetched yet, the endpoint MUST return indicator `unknown` with `stale` true and empty component/incident lists.

#### Scenario: Endpoint returns a degraded snapshot

- **GIVEN** a cached snapshot with indicator `major` and one API incident
- **WHEN** a dashboard client GETs `/api/system-status`
- **THEN** the response indicator is `major`, `stale` is false, and the incident lists its affected components

#### Scenario: Endpoint before the first successful poll

- **GIVEN** no snapshot has been cached
- **WHEN** a dashboard client GETs `/api/system-status`
- **THEN** the response indicator is `unknown`, `stale` is true, and `components`/`incidents` are empty

### Requirement: Upstream-attributable errors are advisorily annotated during API incidents

When the service returns an upstream-attributable failure (upstream 5xx, gateway/bad-gateway, connection error, or timeout) to a downstream client AND the cached snapshot is fresh AND shows a degradation affecting an API/Responses-relevant component, the client-visible error `message` MUST be extended with a concise note identifying OpenAI's status page as the source. The annotation MUST be advisory only: it MUST NOT fail a request that would otherwise succeed, MUST NOT change routing or account selection, and MUST leave the JSON error-envelope structure intact (extending only the human-readable `message`). Annotation MUST be idempotent.

The service MUST NOT annotate failures that are not OpenAI outages: rate-limit or quota failures (including HTTP 429), authentication failures (HTTP 401/403), or client 4xx errors. The service MUST NOT annotate when the snapshot is clear, stale, or absent, or when the only degradation is a ChatGPT-web-only component.

#### Scenario: Gateway error during an API incident is annotated

- **GIVEN** a fresh snapshot with indicator `major` and an incident affecting the API component
- **WHEN** the proxy returns a bad-gateway upstream error to the client
- **THEN** the client-visible message is extended with a note naming the OpenAI API incident and `status.openai.com`
- **AND** the error code, type, and envelope structure are unchanged

#### Scenario: Rate-limit and auth failures are never annotated

- **GIVEN** a fresh snapshot showing an API incident
- **WHEN** the proxy returns a rate-limit (429), quota, or auth (401/403) error
- **THEN** the client-visible message is returned unchanged

#### Scenario: No annotation when status is clear or stale

- **GIVEN** the snapshot indicator is `none`, or the snapshot is stale or absent
- **WHEN** the proxy returns an upstream 5xx error
- **THEN** the client-visible message is returned unchanged

#### Scenario: ChatGPT-web-only incidents do not annotate API errors

- **GIVEN** a fresh snapshot whose only degradation is a ChatGPT-web component
- **WHEN** the proxy returns an upstream 5xx error
- **THEN** the client-visible message is returned unchanged

### Requirement: Dashboard surfaces OpenAI status from the server snapshot

The dashboard MUST display OpenAI status by reading `GET /api/system-status` (not by fetching `status.openai.com` from the browser). When the indicator is clear (`none`) the dashboard MUST show a compact operational indicator. When the indicator is `minor`, `major`, or `critical` the dashboard MUST show an alert banner containing the incident title, the affected component, and a link to `status.openai.com`. When status is unknown or stale, the dashboard MUST NOT assert a status.

#### Scenario: Operational status shows a compact indicator

- **WHEN** `/api/system-status` reports indicator `none` and not stale
- **THEN** the dashboard shows a compact operational indicator and no alert banner

#### Scenario: Degraded status shows an incident banner

- **WHEN** `/api/system-status` reports indicator `major` with an API incident and not stale
- **THEN** the dashboard shows an alert banner with the incident title, affected component, and a `status.openai.com` link

#### Scenario: Stale or unknown status shows nothing

- **WHEN** `/api/system-status` reports `stale` true or indicator `unknown`
- **THEN** the dashboard shows neither the indicator nor a banner
