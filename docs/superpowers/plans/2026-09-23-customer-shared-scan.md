# Customer Shared Scan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow multiple browsers scanning the same signed service-position QR to collaborate on one unsubmitted cart while keeping submitted orders, identities, prices, and feedback private.

**Architecture:** Mint a stateless, browser-bound collaboration token after QR verification and reuse the active occupancy version as the optimistic cart version. Existing selection endpoints accept this token through a separate header; shared writes lock the session and occupancy, compare versions, and return deterministic 409 conflicts. The H5 joins directly into the menu, polls by version, and keeps visit/service feedback as a secondary action.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, React, TypeScript, Node test runner, pytest.

## Global Constraints

- Share only an unsubmitted draft; never expose or directly edit a submitted order.
- Do not rotate the legacy global selection token when another browser joins.
- Every shared write requires optimistic version checking; silent last-write-wins is forbidden.
- No database migration; reuse `PositionOccupancy.version`.
- A collaboration token is bound to the signed QR record, room, session, browser Cookie, mode, and expiry.
- Service review ownership and standalone visit feedback remain unchanged.

---

### Task 1: Contract and token domain

**Files:**
- Create: `hxy-server/app/domain/selection_collaboration_tokens.py`
- Modify: `docs/contracts/customer-shared-selection-v1.md`
- Test: `hxy-server/tests/test_shared_selection_collaboration.py`

**Interfaces:**
- Produces: `create_collaboration_token(...) -> str` and `resolve_collaboration_token(...) -> CollaborationContext`.
- Consumes: active `ServicePositionQr`, `Room`, `SelectionSession`, `PositionOccupancy`, and `hxy_browser_token`.

- [ ] Write tests that reject a token on wrong browser, room, session, inactive QR, replaced active session, expiry, and cross-store access.
- [ ] Run the focused pytest file and verify the missing module/API failures.
- [ ] Implement the signed token and resolver with explicit `COLLABORATION_TOKEN_INVALID` / `COLLABORATION_TOKEN_EXPIRED` errors.
- [ ] Run the focused tests to green and commit the contract/token batch.

### Task 2: Join, versioned writes, and atomic submit

**Files:**
- Modify: `hxy-server/app/api/occupancies.py`
- Modify: `hxy-server/app/api/selections.py`
- Modify: `hxy-server/app/schemas/selection.py`
- Modify: `hxy-server/openapi.json`
- Test: `hxy-server/tests/test_shared_selection_collaboration.py`

**Interfaces:**
- Produces entry fields `collaboration_token`, `collaboration_mode`, `cart_version`, `shared_cart`.
- Accepts `X-Collaboration-Token`, `expected_version`, and `Idempotency-Key` on shared writes.

- [ ] Add failing tests for two browsers joining one draft without legacy token rotation, redacted browse-only entry after submit, cross-room denial, version conflict payload, atomic submit, and idempotent replay.
- [ ] Run focused tests and verify each fails for missing shared behavior.
- [ ] Implement join semantics and independent token issuance.
- [ ] Implement locked GET/PATCH/submit authorization, optimistic version increments, 409 latest snapshot, and submitted redaction.
- [ ] Run focused tests plus existing selection and visit-feedback suites; update generated OpenAPI and commit.

### Task 3: Direct menu and client synchronization

**Files:**
- Create: `diy-web/src/sharedSelection.ts`
- Modify: `diy-web/src/api.ts`
- Modify: `diy-web/src/App.tsx`
- Modify: `diy-web/src/styles.css`
- Test: `diy-web/tests/shared-selection.test.ts`

**Interfaces:**
- Produces a 3-second visible-page synchronizer keyed by `cart_version`.
- Consumes the collaboration response fields and conflict snapshot from Task 2.

- [ ] Write failing tests for QR-first menu routing, collaboration headers/version payloads, polling pause/resume, conflict reconciliation, submitted locking, and secondary feedback entry.
- [ ] Run the focused Node test and verify expected failures.
- [ ] Add API types/helpers and pure synchronization/reconciliation functions.
- [ ] Update App initialization to enter the menu directly, show the shared notice, refresh by version, and avoid direct-feedback boot.
- [ ] Run focused and full customer tests, build, verify 320/390px layouts, and commit.

### Task 4: Governance and delivery verification

**Files:**
- Modify: `docs/TEAM-MEMORY.md`
- Modify: `docs/workstreams/customer.md`
- Modify: `docs/contracts/open-visit-feedback-v1.md`
- Test: relevant contract, backend, and customer suites.

**Interfaces:**
- Produces one PR containing implementation, generated OpenAPI, contracts, tests, and workstream evidence.

- [ ] Record the shared-draft boundary, residual static-QR risk, and unchanged feedback ownership.
- [ ] Run backend focused suites, customer full tests/build, contract checks, and `git diff --check`.
- [ ] Review the final diff for generated files, secrets, migration absence, and cross-end contract consistency.
- [ ] Commit, push the exact HEAD, create the PR, wait for required CI, and report local/PR/merge/production/field-acceptance states separately.
