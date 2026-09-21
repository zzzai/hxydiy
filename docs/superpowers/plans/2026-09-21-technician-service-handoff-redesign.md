# Technician Service Handoff Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the technician post-service tag form with a fast v7 handoff, remove internal English IDs from service orders, and scan membership codes before choosing a service order.

**Architecture:** Add one strict v7 schema and reuse the existing profile-record table, permissions, idempotency, audit, history, and correction paths. Build a focused React handoff sheet that maps stable codes to Chinese copy. Reorder membership verification in the existing frontend without weakening backend consume-time checks.

**Tech Stack:** React, TypeScript, Ant Design, FastAPI, Pydantic v2, SQLAlchemy, Node test runner, pytest.

## Global Constraints

- New writes use `schema_version=7` and `taxonomy_version=service_handoff_v1`; v1–v6 remain read-only compatible.
- Visible technician copy is Chinese; internal IDs and stable codes are never rendered.
- Age values are `age_25_29`, `age_30_34`, `age_35_39`, `age_40_44`, `age_45_49`, `age_50_59`, `age_60_plus`; gender values are only `male` and `female`.
- Basic information is optional even though the UI has no explicit “不记录” choice.
- Preserve store isolation, role checks, service-state checks, idempotency, audit, one-correction semantics, and privacy redaction.

---

### Task 1: V7 service-handoff contract

**Files:**
- Create: `hxy-server/app/schemas/service_handoff.py`
- Modify: `hxy-server/app/api/admin_v2.py`
- Modify: `hxy-server/app/api/technician.py`
- Test: `hxy-server/tests/test_technician_service_handoff_v7.py`

**Interfaces:**
- Produces `ServiceHandoffRecord`, `safe_handoff_lines(raw: dict) -> list[str]`, and v7 create/history/reference responses.

- [ ] Write failing tests for accepted age/gender codes, paired `region + next_action`, maximum three body entries, empty/no-new exclusivity, forbidden unknown fields, technician ownership, store isolation, idempotency, and one correction.
- [ ] Run `pytest hxy-server/tests/test_technician_service_handoff_v7.py -q` and verify failures are caused by missing v7 support.
- [ ] Implement strict Pydantic models and wire v7 through request validation, payload storage, safe summaries, own history, service-before reference, and management redaction.
- [ ] Re-run the focused test until it passes.
- [ ] Commit with `git commit -m "feat(technician): add v7 service handoff contract"`.

### Task 2: Fast handoff interface

**Files:**
- Create: `admin-react/src/technician/serviceHandoff.ts`
- Create: `admin-react/src/technician/TechnicianServiceHandoffSheet.tsx`
- Create: `admin-react/src/technician/service-handoff.css`
- Modify: `admin-react/src/technician/TechnicianProfileSheet.tsx`
- Modify: `admin-react/src/technician/TechnicianServiceHistoryPage.tsx`
- Test: `admin-react/tests/service-handoff.test.ts`
- Test: `admin-react/tests/technician-workspace.test.ts`

**Interfaces:**
- Produces `makeServiceHandoff()`, `buildServiceHandoffPayload()`, `buildHandoffPreview()`, and the v7 sheet.

- [ ] Write failing unit tests for exact stable codes, age/gender omission when unselected, body-action pairing, project-aware change options, preview text, no-new behavior, and payload idempotency inputs.
- [ ] Run `npm test -- --test-name-pattern="service handoff|移动技师"` in `admin-react` and verify expected failures.
- [ ] Implement the selected mobile design with live handoff preview, compact choices, optional basic info, body/action pairs, hidden private note, confirmation, preserved drafts, and retry behavior.
- [ ] Update new-record routing so all new writes use v7 while v5/v6 remain historical correction/read compatibility.
- [ ] Re-run focused tests and `npm run build`.
- [ ] Commit with `git commit -m "feat(technician): redesign post-service handoff"`.

### Task 3: Chinese-only service order presentation

**Files:**
- Modify: `admin-react/src/technician/TechnicianTodayPage.tsx`
- Test: `admin-react/tests/technician-workspace.test.ts`

**Interfaces:**
- Keeps internal occupancy keys internal; renders only room name, project summary, and Chinese status.

- [ ] Write a failing test asserting the drawer does not render `#`, `position-`, occupancy IDs, or raw status codes.
- [ ] Run the focused frontend test and verify it fails on the current title/header.
- [ ] Replace the title and header with `顾客服务单`, Chinese room name, project summary, and translated state only.
- [ ] Re-run the focused test.
- [ ] Commit with `git commit -m "fix(technician): hide internal service order ids"`.

### Task 4: Scan-first membership verification

**Files:**
- Modify: `admin-react/src/technician/TechnicianMembershipVerifyPage.tsx`
- Modify: `admin-react/src/technician/technician-mobile.css`
- Test: `admin-react/tests/technician-membership-verify.test.ts`

**Interfaces:**
- Scans first, then loads/selects `Candidate`; consumes through the unchanged `consumeMembershipCode(codeToken, selectionSessionId)` boundary.

- [ ] Write failing tests proving camera start does not require a selection, candidate selection appears only after scan, one candidate auto-selects, multiple candidates require an explicit choice, and consume remains disabled without a candidate.
- [ ] Run the focused test and verify expected failures.
- [ ] Reorder state and UI: scan, show member, load candidates, auto-select one, choose among many, then consume; preserve scan token across candidate-load retry.
- [ ] Re-run the focused test and frontend build.
- [ ] Commit with `git commit -m "feat(technician): verify membership before order selection"`.

### Task 5: Shared contracts and release evidence

**Files:**
- Create: `docs/contracts/technician-service-handoff-v1.md`
- Modify: `docs/contracts/customer-membership-verification.md`
- Modify: `docs/TEAM-MEMORY.md`
- Modify: `docs/workstreams/technician.md`

**Interfaces:**
- Documents the v7 payload, visibility matrix, correction rules, and scan-first flow.

- [ ] Write the executable contract tables and acceptance cases; explicitly prohibit conversion to marketing tags or pricing features.
- [ ] Run `git diff --check` and search the changed technician UI for `position-|服务单 #|schema_version` visible copy.
- [ ] Commit with `git commit -m "docs: define technician service handoff v7"`.

### Task 6: Integrated verification and delivery

**Files:**
- Modify only files required by failures found in this task.

- [ ] Run focused backend tests for v7, history, technician portal, and membership verification.
- [ ] Run the full frontend test suite and production build.
- [ ] Run the risk-relevant backend suite and `git diff --check`.
- [ ] Render the 390px flow, exercise selections, no-new, save failure/retry, close protection, service-order drawer, and scan-first membership states; record any environment limit separately.
- [ ] Use `tools/release/` to create/monitor the authorized PR and report local, pushed, merged, production, and field-acceptance states separately.

