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

## Verified production handoff (2026-10-06, readonly inspection)

- Unit: `/etc/systemd/system/tcm-webhook.service`; working directory `/opt/tcm-ingest`; private environment file `/etc/tcm-ingest.env` (required). No environment values were read.
- Actual startup: `/opt/tcm-ingest/.venv/bin/uvicorn main:app --host 172.18.0.1 --port 18090 --workers 1 --no-access-log --no-proxy-headers`. Preserve these options. stdout goes to journal; do not add request/header/body/error payload logging.
- Source mount point: `/opt/tcm-ingest/main.py`, immediately after the `app = FastAPI(...)` declaration (inspected at lines 244–245), before middleware/routes. Existing `db` and `settings` imports are already available. `config.py` loads the local `.env` with dotenv, while systemd provides `/etc/tcm-ingest.env`; prefer the existing systemd environment file for the new credential, avoid conflicting duplicate values.
- Reader credential name on **both** services: `TCM_REPORTS_READ_TOKEN`. Generate one new independent 32-byte-or-stronger random credential and privately provision it to TCM and DIY, never the frontend. TCM existing privileged names are `ADMIN_TOKEN` and `WEBHOOK_TOKEN`, accessed as `settings.admin_token` and `settings.webhook_token`. Do not change them. DIY `TCM_REPORTS_BASE_URL` remains exactly `http://172.18.0.1:18090`.

Minimal reviewed mount (operator only, after confirming the active SQLAlchemy engine is file-backed SQLite):

```python
from readonly_reports import build_router

app.include_router(build_router(
    db.engine.url.database,
    os.environ.get('TCM_REPORTS_READ_TOKEN', ''),
    (settings.admin_token, settings.webhook_token),
))
```

Do not substitute `settings.data_dir / 'tcm.db'` without checking the active engine: `DATABASE_URL` can override it. Reject a non-SQLite or in-memory engine during installer preflight, rather than changing the ingestion database. Verify the active file's schema/index using only SQLite PRAGMA statements. No index write has been performed by this development task.

### Actual public proxy and logging

The live proxy is the `hetang-nginx` container. Its host bind source is `/root/hetang-yuese-investment/nginx-proxy.conf`, mounted read-only as `/etc/nginx/conf.d/default.conf`; host `/etc/nginx/sites-enabled/default` is not the TCM site's active configuration.

In the `tcm.hexiaoyue.com` server blocks (inspected lines 598–645), HTTP already returns 404 except ACME. HTTPS proxies **only exact** `/api/tcm/webhook/push` and `/health`; `location / { return 404; }` blocks all other paths. Both blocks use `access_log off; error_log /dev/null crit;`. Keep these existing limits; no nginx change is required to expose the reader, and the reader must never be exposed. Optional explicit defense-in-depth, if the coordinator chooses to change the proxy:

```nginx
location = /api/tcm/readonly { return 404; }
location ^~ /api/tcm/readonly/ { return 404; }
```

The precise forbidden namespace is `/api/tcm/readonly` and everything below `/api/tcm/readonly/`, not the customer-facing DIY `/api/v1/me/tcm-reports` paths. Do not block the latter, or broaden the existing webhook location. Recheck every future vhost/alias forwarding to port 18090. Do not enable debug/error/header logs for this namespace; the existing error-log suppression is a privacy tradeoff already present, not an instruction to disable unrelated operational monitoring.

### Minimal installation / rollback checklist

1. Coordinator records the exact reviewed commit/module digest and backs up original `main.py`, configuration and SQLite using a consistent SQLite backup, with a verified restore copy outside Git. Do not copy a live WAL database with plain file copy.
2. Check active SQLite path/schema/phone index, private bind and current proxy restrictions. Copy only the module, apply the mount above, privately add the independent key to `/etc/tcm-ingest.env` with root-only permissions. Compile the two Python files with the service venv; do not run an ingestion replay or init migration as a validation shortcut.
3. Coordinator restarts **only** `tcm-webhook.service`, checks internal `/health`, and confirms public readonly routes still return 404 without submitting health data. Verify missing/wrong/reused privileged credentials are denied, list/detail owner checks and limits against synthetic fixtures. Avoid real report bodies in terminal or evidence.
4. Only then provision the same independent key in DIY's existing private server configuration and use the normal reviewed DIY deployment workflow. The TCM module does not deploy with the DIY container automatically. Preserve all existing credentials and container volumes. Confirm actual runtime access and customer consent behavior separately from CI; human device acceptance remains outstanding.
5. Rollback order: disable DIY `TCM_REPORTS_READ_TOKEN` through its normal deployment/restart path, restore original TCM `main.py`, remove only the new read-token configuration and restart `tcm-webhook.service`; verify original health/ingestion boundaries. Keep backup and module evidence; no report deletion or database restore is needed for this read-only increment. If actual database integrity differs, stop and escalate rather than automatically restoring or replaying reports.

### Exact development evidence

- PR #198 implementation HEAD `be384a483588fb31e4c6f75d88e6e66233f2be84`.
- GitHub CI for that exact HEAD: success, run `37454170530`, https://github.com/zzzai/hxydiy/actions/runs/37454170530 . Local and server isolated tests: 41 unique tests and 9 auth subtests passed (38 tests followed by 5 source tests, with 2 repeated).
- Local watcher report: `C:/Users/gaoji/Documents/ChatGPT/hxy-diy/.git/hxy-release-reports/pr-198-be384a483588fb31e4c6f75d88e6e66233f2be84/report.json`; the inspected snapshot was nonterminal `connection_retry`/`URLError`, so it is **not** final CI evidence. The GitHub run above was checked directly instead.
- Isolated server fixture source: `/tmp/hxy-tcm-my-reports.U7rlqI`, container `diy-api`, `--network none --read-only --tmpfs /tmp`, only temporary readonly source/dependencies mounted; no production database or secrets mounted. Temporary dependencies reused `/tmp/hxy-menu-20261001.HF4VP6/deps`.
- No production module install, secret write, service restart, report read/write or deployment performed by this writer.
