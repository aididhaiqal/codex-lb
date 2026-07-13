## 1. Status poller (backend)

- [x] 1.1 Add outbound client `app/core/clients/openai_status.py` (aiohttp + `lease_retry_client`) that GETs `https://status.openai.com/api/v2/summary.json` with a short timeout, parses indicator/components/unresolved-incidents, and raises `OpenAIStatusFetchError` on any transport/HTTP/parse failure
- [x] 1.2 Add process-local, thread-safe snapshot holder `app/core/openai/status_state.py` with last-updated timestamp + age-derived staleness, and API-relevance helpers (components/incidents mentioning "api"; ChatGPT-web-only excluded)
- [x] 1.3 Add `app/core/openai/status_scheduler.py` (`build_openai_status_scheduler`, ~60s, not leader-gated) that records success or keeps the previous snapshot on failure; wire start/stop into `app/main.py` lifespan; add `openai_status_*` settings
- [x] 1.4 Disable the scheduler and reset the store between tests via autouse fixtures in `tests/conftest.py`

## 2. Endpoint + dashboard banner

- [x] 2.1 Add `app/modules/system_status/` (`api.py`/`schemas.py`/`service.py`) exposing `GET /api/system-status`; register the router in `app/main.py`
- [x] 2.2 Add `frontend/src/features/system-status/` widget reading `/api/system-status` via the react-query api client; clear dot when operational, alert banner (title + affected component + status.openai.com link) when degraded; place it in the dashboard header
- [x] 2.3 Add the MSW default handler + factory + handler-coverage entry for `GET /api/system-status`

## 3. Error enrichment (advisory)

- [x] 3.1 Add `app/core/openai/status_annotation.py` with `maybe_annotate_upstream_error` / `annotate_upstream_error_message` gated to upstream-attributable failures and API-affecting, non-stale snapshots; never raises
- [x] 3.2 Call the helper at the single downstream error-message funnel (`app/core/errors.py::openai_error`, which also backs streaming `response_failed_event`), leaving the JSON envelope structure intact

## 4. Tests

- [x] 4.1 Client/parser: sample `summary.json` extracts indicator/components/unresolved incidents; fetch fails gracefully on HTTP/transport errors
- [x] 4.2 Enrichment gating: enriches 5xx/gateway during an API incident; does NOT enrich 429/quota/auth/4xx, clear status, stale snapshot, or ChatGPT-only incidents; idempotent
- [x] 4.3 Endpoint returns the cached snapshot (and `unknown`/stale when empty)
- [x] 4.4 Frontend: banner renders on degraded, dot on clear, nothing when stale

## 5. Validation

- [x] 5.1 `uv run pytest tests/unit` (new suites), `make frontend-build`, `ruff`, `ty`
- [x] 5.2 `openspec validate --specs`
