# Offline TCM readonly increment

This directory is an offline increment, not a production deployment. Do not copy the private source snapshot, runtime `.env`, databases or vendor reports into Git.

## Operator installation boundary

1. Back up the deployed `/opt/tcm-ingest` source and SQLite database, verify restoration, and compare the current schema with the module queries. Confirm an existing `(phone, report_time)` index; any missing-index schema write requires the coordinated backup/change procedure.
2. Run `test_readonly_reports.py` against an isolated fixture database before installation. Copy only `readonly_reports.py`, verify its digest, and minimally mount `build_router(actual_database_path, dedicated_read_token, (existing_admin_token, existing_webhook_token))` in the actual FastAPI app. The third argument is mandatory. Use the actual runtime configuration; do not assume file names/settings types or copy the external project.
3. Generate an independent high-entropy read token server-side in private configuration. Never reuse webhook/admin credentials or print tokens in commands/logs. Configure DIY `TCM_REPORTS_READ_TOKEN` privately only after the reader is validated. Empty token means disabled. Existing ingestion code, admin endpoints, report contents and tables remain unchanged.
4. Keep the service bound to its internal address. Explicitly deny `/api/tcm/readonly/` in all public reverse proxies. Loopback is accepted for internal checks, so proxy blocking is essential; source-IP checks alone do not block a public localhost proxy. Ignore caller forwarded IPs.
5. Exclude this namespace from access/request-body/header logs (including IDs and the verified-phone header); never log response bodies or exceptions containing private payloads. The phone header avoids default URL logging but does not make arbitrary header logging safe.
6. Only the coordinated installer may restart `tcm-webhook.service`. Check ingestion health and existing authentication behavior; perform new-reader credential/network/bounds/ownership checks with synthetic fixtures, not a real webhook probe. No bulk personal report fetches for validation.
7. Enable DIY only after internal validation. Rollback by disabling its read token/removing the new router, retaining existing ingestion. No customer import, SMS, WeCom delivery, clinical output or photos in this increment.

## Read contract

See `docs/contracts/tcm-my-reports-v1.md`. SQLite connections use read-only URI mode, query-only protection and bounded parameterized selects. `X-TCM-Verified-Phone` is supplied by the trusted DIY backend, never the browser. Dedicated Bearer auth and actual socket peer restrictions are both required. Whitelisted detail fields never include phone, name, media, links or raw structured data.

The backend test wrapper `hxy-server/tests/test_tcm_source_contract.py` executes these fixture tests in normal backend CI. Direct isolated execution: `python -m pytest tools/integrations/tcm/test_readonly_reports.py -q` with FastAPI/httpx/pytest installed.
