# Open Visit Feedback Implementation Plan

> **For agentic workers:** Use executing-plans to implement the assigned tasks. Steps use checkbox syntax for tracking.

**Goal:** Deliver production-ready feedback from the existing QR entry for anonymous and signed-in customers, regardless of selection or service-order status.

**Architecture:** Keep verified completed-service feedback and its ownership rules. Add separately persisted unlinked visit feedback, a real admin handling surface, and an always-available customer entry. The backend is the single owner of identity, store authorization, idempotency, and API schemas.

**Tech Stack:** Existing FastAPI/SQLAlchemy/PostgreSQL/Alembic backend; React/TypeScript customer and admin applications; HTTP contract tests, browser checks, protected release scripts.

## Approved product scope

- Feature ID: CUSTOMER-FEEDBACK-005. Approved on 2026-09-21 in the total-control task.
- One existing QR code opens the existing menu; a visible “评价与建议” entry works without login, a selected project, or a service order.
- An in-progress service does not prevent independent visit feedback.
- Explicit integer rating 1–5, no preselected rating, at most three permitted tags and 300 characters of optional text. Do not require telephone details.
- Preserve selections on opening, dismissing, failure and successful feedback submission. Success offers continued shopping.
- Keep verified completed-service feedback separately attributable. Never derive an order, customer or technician from the occupied seat.
- Unlinked visit feedback is visible to authorized store management, distinguishable from verified service feedback, and excluded from technician ratings.
- Repeated clicks, transport retries and concurrent identical requests must not create duplicate feedback. Server-side rate limiting must work across workers and return a clear retry response.
- Supersedes the old shared-QR proposal's restriction that only completed-service customers may evaluate. Its ownership protections remain valid for linked feedback. A pending-service reminder is auxiliary and must not gate the permanent entry.
- No demo data, fake service orders, inert admin controls, or production credentials in artifacts.

## Ownership and dependencies

- Management/backend task owns backend code, migration, API schemas, admin feedback UI and contract documentation.
- Customer task owns diy-web entry, form, API consumption and customer verification.
- Technician task independently reviews identity, store isolation, score attribution and backward compatibility; no shared implementation writes.
- Total control owns integration, release evidence and final acceptance status.
- PR #130 and #132 are separate existing work. Do not merge unrelated work by assumption or overwrite their worktrees. Use latest main; resolve any App overlap explicitly at integration.
- BRAND-CATALOG-004 business implementation waits while this feedback task owns shared backend files.

## Task 1: Freeze the implementable contract

**Files:** Existing `hxy-server/app/models/feedback.py`, `app/api/selections.py`, `app/api/admin_v2.py`, `diy-web/src/components/FeedbackDialog.tsx`; create `docs/contracts/open-visit-feedback-v1.md`.

- [ ] Inspect current feedback ownership, browser identity, tag validation, follow-up permissions and score aggregations.
- [ ] Backend publishes exact request/response/error/identity and retry semantics to the customer task before integration. Keep UI implementation independent while this is prepared.
- [ ] Specify unlinked persistence and source discrimination without weakening the existing ServiceFeedback endpoint. Reuse existing follow-up states if they apply; do not invent an automatic outreach promise.
- [ ] Resolve existing frontend/backend 3/300 versus 6/1000 validation drift in the contract with regression tests; preserve readable historical records.

## Task 2: Persist and manage real feedback

**Files:** Backend-owned feedback model/schema/router/domain modules; models registration and router registration; Alembic migration if required; admin feedback list/model; `hxy-server/tests/test_open_visit_feedback.py`; related existing feedback tests.

- [ ] Add failing real HTTP tests for anonymous/no order, logged-in/no order, ongoing service, invalid identity, wrong store, invalid rating/tags/text, duplicate retries, conflicting payload with reused key, and concurrent writes.
- [ ] Implement server-validated QR/store context and explicit identity precedence. An invalid supplied login credential must not silently become an anonymous request.
- [ ] Persist before success; enforce idempotency in the database, with the request body bound to the key and retries returning the saved result.
- [ ] Add bounded rate limiting with shared storage and test quota exhaustion/recovery. Do not rely solely on a frontend timer or process-local counter.
- [ ] Add real store-scoped admin list/detail and follow-up integration, with source labels and audit. Verify another store cannot read or handle the entry.
- [ ] Verify old service feedback ownership/completion and technician statistics remain intact. Run meaningful PostgreSQL concurrency and migration checks.
- [ ] Export OpenAPI and generate types; update TEAM-MEMORY and the management workstream in the same business PR.

## Task 3: Customer entry and production integration

**Files:** `diy-web/src/App.tsx`, `src/components/FeedbackDialog.tsx` or a focused visit-feedback component, `src/api.ts`, focused state/helper module, customer tests, customer workstream.

- [ ] Test a permanently visible entry for anonymous and signed-in visitors with empty selections and no service order.
- [ ] Connect to the real frozen API; maintain a submission idempotency key across retries and replace it only for a new submission intent.
- [ ] Keep unlinked feedback and verified-service submission modes explicit. Do not send untrusted session/technician attribution from the seat.
- [ ] Test failure input retention, retry, duplicate clicks, stale identity/store response rejection, close/reopen behavior, and retained shopping draft.
- [ ] Run the customer tests/build and local browser flows with the implemented backend. Browser checks must include narrow-screen layout, focus/keyboard access and no forced login/project selection.
- [ ] Submit an independent PR with exact backend dependency and evidence. Integration must use the final backend HEAD, not mocks.

## Task 4: Independent review and release

- [ ] Review final exact HEADs for anonymous abuse controls, identity precedence, cross-store access, idempotency races, no seat-based attribution and correct statistics separation.
- [ ] Resolve findings with regression tests. Required CI must pass for each final HEAD.
- [ ] Produce a migration-impact report if schema changes: touched tables, retained rows, backup/restore rehearsal, upgrade evidence and rollback strategy preserving newly submitted feedback.
- [ ] Follow protected release scripts and applicable authorization. Confirm production migration authority against the concrete impact before any database change requiring separate approval.
- [ ] Verify deployed SHA, server current, health and assets; use designated test context for real anonymous no-order submit and admin visibility/handling. Do not pollute unrelated live service records.
- [ ] Record what was locally tested, merged, deployed and production-verified. Real WeChat/device/weak-network/store acceptance remains explicit until actually performed.

## Completion criteria

A fresh browser can scan the existing valid entry and submit feedback without login, selecting a project or creating a service order; the feedback survives reload and is visible only to authorized management of the correct store. Original linked evaluation and technician score attribution remain correct. Tests, independent review, CI and deployment evidence are complete; any unavailable field verification is explicitly identified rather than claimed.
