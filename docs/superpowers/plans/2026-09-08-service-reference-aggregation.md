# Service Reference Aggregation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide managers a store-scoped, privacy-safe count, confirmation rate, and correction rate for structured service references.

**Architecture:** Add one manager-only aggregate endpoint in `admin_v2.py`. It reads `CustomerProfileRecord` rows only from the authenticated staff member’s store and returns numeric aggregates for schema versions 3–5, excluding superseded records. The existing analytics page consumes only the aggregate numbers; it receives no customer, quote, profile, body-point, price, or free-text data.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic-style JSON responses, React, TypeScript, Node test runner, pytest.

## Global Constraints

- Only `admin` and `manager` may access the aggregate endpoint; ordinary `staff` remains default-deny read-only.
- Do not expose records, customer identifiers, quotes, profile payloads, body notes, technician notes, prices, or raw labels.
- Aggregate only `schema_version` 3, 4, and 5 records in the authenticated store.
- A record referenced by a later correction must not count as current; the correction record itself counts.
- No new migration, no customer/technician route change, no physical-resource action, and no production release from this task.

---

### Task 1: Store-scoped aggregate API contract

**Files:**
- Modify: `hxy-server/app/api/admin_v2.py`
- Test: `hxy-server/tests/test_customer_profile_records_api.py`
- Modify: `docs/contracts/service-reference-v2.md`

**Interfaces:**
- Consumes: `GET /api/v1/admin/v2/service-reference-summary` with staff bearer authentication.
- Produces: `{ "total": int, "confirmed": int, "confirmation_rate_percent": float, "corrected": int, "correction_rate_percent": float }`.

- [x] **Step 1: Write the failing API test**

```python
response = client.get('/api/v1/admin/v2/service-reference-summary', headers=manager_headers)
assert response.status_code == 200
assert response.json() == {
    'total': 2,
    'confirmed': 1,
    'confirmation_rate_percent': 50.0,
    'corrected': 1,
    'correction_rate_percent': 50.0,
}
```

Also seed an old record whose `id` is referenced by a later correction and a different-store record; assert neither inflates `total`.

- [x] **Step 2: Verify the test fails**

Run: `python -m pytest tests/test_customer_profile_records_api.py -k service_reference_summary -q`

Expected: `404` because the endpoint does not exist.

- [x] **Step 3: Implement the minimal aggregate**

```python
@router.get('/service-reference-summary')
def service_reference_summary(...):
    staff = _current_staff(authorization, db)
    _require_admin(staff)
    store_id = _staff_store_id(staff)
    superseded = select(CustomerProfileRecord.correction_of_id).where(
        CustomerProfileRecord.store_id == store_id,
        CustomerProfileRecord.correction_of_id.is_not(None),
    )
    records = list(db.scalars(select(CustomerProfileRecord).where(
        CustomerProfileRecord.store_id == store_id,
        CustomerProfileRecord.schema_version.in_([3, 4, 5]),
        CustomerProfileRecord.id.not_in(superseded),
    )))
```

Compute rates as `0.0` when `total == 0`, otherwise round to two decimals. Return only the five documented numeric fields.

- [x] **Step 4: Verify the API test passes**

Run: `python -m pytest tests/test_customer_profile_records_api.py -k service_reference_summary -q`

Expected: PASS.

- [x] **Step 5: Document the contract**

Add the endpoint, numerical response shape, manager-only access, store isolation, eligible versions, and explicit exclusion of sensitive fields to `docs/contracts/service-reference-v2.md`.

- [x] **Step 6: Commit**

```bash
git add hxy-server/app/api/admin_v2.py hxy-server/tests/test_customer_profile_records_api.py docs/contracts/service-reference-v2.md
git commit -m "feat(admin): add service reference summary"
```

### Task 2: Management analytics presentation

**Files:**
- Modify: `admin-react/src/api.ts`
- Modify: `admin-react/src/pages/AnalyticsPage.tsx`
- Test: `admin-react/tests/analytics-page.test.ts`

**Interfaces:**
- Consumes: `getServiceReferenceSummary(): Promise<{ data: ServiceReferenceSummary }>`.
- Produces: A manager analytics card displaying only total, confirmed count, confirmation rate, and correction rate.

- [x] **Step 1: Write the failing page/API test**

```typescript
assert.match(source('api.ts'), /getServiceReferenceSummary/);
assert.match(source('pages/AnalyticsPage.tsx'), /服务参考/);
assert.doesNotMatch(source('pages/AnalyticsPage.tsx'), /quote|body_service_notes|service_note/);
```

- [x] **Step 2: Verify the test fails**

Run: `node --experimental-strip-types --test tests/analytics-page.test.ts`

Expected: FAIL because the API function and card are absent.

- [x] **Step 3: Implement the minimal read-only card**

```typescript
export const getServiceReferenceSummary = () => client.get('/admin/v2/service-reference-summary');
```

Load it alongside existing analytics requests. Render four `Statistic` values in a card titled `服务参考（门店汇总）`; keep the existing error behavior and do not add a drill-down link.

- [x] **Step 4: Verify frontend tests and type checking**

Run: `npm test -- --runInBand; npx tsc -b`

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add admin-react/src/api.ts admin-react/src/pages/AnalyticsPage.tsx admin-react/tests/analytics-page.test.ts
git commit -m "feat(admin): show service reference summary"
```

### Task 3: Cross-contract verification and handoff

**Files:**
- Modify: `docs/TEAM-MEMORY.md`
- Modify: `docs/workstreams/admin.md`

**Interfaces:**
- Consumes: the Task 1 endpoint and Task 2 card.
- Produces: an explicit local-only implementation record and release/field-acceptance boundary.

- [x] **Step 1: Run targeted backend regression**

Run: `python -m pytest tests/test_customer_profile_records_api.py tests/test_admin_resource_permissions.py -q`

Expected: PASS, with only documented existing warnings.

- [x] **Step 2: Run static diff validation**

Run: `git diff --check`

Expected: no output other than line-ending notices.

- [x] **Step 3: Update shared memory**

Record that the aggregate is manager-only, store-isolated, numeric-only, excludes superseded records and all sensitive service-reference content, and is not production evidence.

- [x] **Step 4: Commit**

```bash
git add docs/TEAM-MEMORY.md docs/workstreams/admin.md
git commit -m "docs(admin): record service reference summary boundary"
```

## Self-Review

- Spec coverage: covers the workstream’s first-phase distribution/confirmation/correction aggregate; deliberately excludes complex taxonomy configuration, real-time warehousing, raw record drill-down, and customer profiling.
- Sensitive-data coverage: Task 1 returns only five numbers; Task 2 has a source-level regression guard against sensitive fields.
- Type consistency: `ServiceReferenceSummary` is the single frontend response type; all rates are percentages in the range 0–100.

## Execution Handoff

Plan saved to `docs/superpowers/plans/2026-09-08-service-reference-aggregation.md`. Execute inline in this isolated worktree with test-first steps; do not create a production release from this plan.
