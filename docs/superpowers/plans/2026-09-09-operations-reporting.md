# Operations Reporting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add completed-service project sales and technician workload metrics to the existing admin operations summary.

**Architecture:** Extend the existing store-scoped operations-summary aggregation from completed position occupancies. The API returns non-sensitive ranked rows; the existing analytics page renders them for its selected date range.

**Tech Stack:** FastAPI, SQLAlchemy, pytest, React, TypeScript, Vitest, Ant Design.

## Global Constraints

- Count only occupancies whose `actual_service_end_at` is in the selected inclusive date range.
- Keep the existing manager/store scope; do not add financial, customer, export, migration, or 智慧宝 behavior.
- Use stored item names/quantities and never infer an unassigned technician.

---

### Task 1: Add the API aggregation contract

**Files:**
- Modify: `hxy-server/tests/test_api_contracts.py`
- Modify: `hxy-server/app/api/admin.py`

**Interfaces:**
- Produces `project_sales_top5: [{name: str, quantity: int}]` and `technician_service_counts: [{technician_id: int, name: str, completed_services_count: int}]` in `GET /api/v1/admin/operations-summary`.

- [ ] **Step 1: Write the failing contract test**

Create completed, in-range occupancies for one store, with session item snapshots and two assigned technicians. Assert quantities are merged by stored name, results are ranked, a different-store record and an unfinished occupancy are absent, and an unassigned completed occupancy is absent from technician rows.

- [ ] **Step 2: Verify the test is red**

Run: `python -m pytest tests/test_api_contracts.py -k operations_summary_reports_project_sales_and_technician_volume -q`

Expected: FAIL because the response lacks `project_sales_top5` and `technician_service_counts`.

- [ ] **Step 3: Implement the minimal aggregation**

Read completed occupancies within the existing selected store/date range, load their selection sessions and technicians, aggregate safe snapshot fields, and append the two arrays to the existing summary response.

- [ ] **Step 4: Verify the contract is green**

Run: `python -m pytest tests/test_api_contracts.py -k operations_summary -q`

Expected: PASS.

### Task 2: Render the two report tables

**Files:**
- Modify: `admin-react/src/pages/AnalyticsPage.tsx`
- Test: `admin-react/tests/analytics-page.test.tsx`

**Interfaces:**
- Consumes the two response arrays from Task 1.
- Produces read-only “项目销量 Top5” and “技师服务量 Top5” tables with empty states.

- [ ] **Step 1: Write the failing component test**

Mock the existing analytics requests with ranked rows and assert both headings and each safe displayed value. Add a no-row fixture and assert the empty-state copy.

- [ ] **Step 2: Verify the test is red**

Run: `npm test -- --run tests/analytics-page.test.tsx`

Expected: FAIL because neither report table exists.

- [ ] **Step 3: Implement minimal rendering**

Add two small Ant Design tables beneath the existing operations panels. Reuse the selected date range's summary response and do not add client-side calculations or new API requests.

- [ ] **Step 4: Verify the component is green**

Run: `npm test -- --run tests/analytics-page.test.tsx`

Expected: PASS.

### Task 3: Run targeted regression checks

**Files:**
- Modify only files from Tasks 1–2 as required by verification.

- [ ] **Step 1: Run backend and frontend targeted suites**

Run: `python -m pytest tests/test_api_contracts.py -k operations_summary -q`; `npm test -- --run`; `npx tsc -b --pretty false`; `git diff --check`.

- [ ] **Step 2: Commit the implementation**

Run: `git add hxy-server/app/api/admin.py hxy-server/tests/test_api_contracts.py admin-react/src/pages/AnalyticsPage.tsx admin-react/tests/analytics-page.test.tsx docs && git commit -m "feat(admin): add operations reporting metrics"`.
