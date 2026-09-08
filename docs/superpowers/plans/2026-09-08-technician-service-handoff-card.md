# Technician Service Handoff Card Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the broad post-service profile form with a fast service-handoff card that records a useful fact, an explicit no-update outcome, or a later-record state.

**Architecture:** Keep schema version 5 and extend only `technician_observed` with `service_note` and `recording_outcome`. React builds the v5 payload from optional service facts and keeps failed input for idempotent retry. The history endpoint returns note text only to the technician who wrote it; management and cross-technician summaries remain redacted.

**Tech Stack:** React, Ant Design, TypeScript, FastAPI, Pydantic v2, SQLAlchemy, pytest, Vitest.

## Global Constraints

- New writes stay at `schema_version=5` and `taxonomy_version=service_reference_v4`; v1-v4 remain read-only compatible.
- `service_note` is at most 200 characters, is technician-recorded context rather than a customer quote, and uses the existing sensitive-text validation.
- `recording_outcome="no_additional_notes"` cannot coexist with tags, note text, body notes, or `customer_confirmed=true`.
- Do not collect demographics, family status, income, broad lifestyle labels, AI inferences, recordings, or automated marketing/price fields.
- Management responses and cross-technician summaries never expose note text; body details keep current v5 safe-summary behavior.
- Test every new behavior red before its production implementation and run targeted then full relevant test suites.

## File Structure

- `admin-react/src/technician/serviceReference.ts`: frontend input and schema-v5 payload builder.
- `admin-react/src/technician/TechnicianProfileSheet.tsx`: mobile service-handoff card and retry behavior.
- `admin-react/src/technician/TechnicianServiceHistoryPage.tsx`: writer-only history completion and note display.
- `admin-react/src/serviceReferenceDisplay.ts`: safe display mapping for completion outcome only.
- `hxy-server/app/api/admin_v2.py`: v5 Pydantic validation and management redaction.
- `hxy-server/app/api/technician.py`: writer-only history projection.
- `admin-react/tests/technician-minimal-note.test.ts`: payload builder unit behavior.
- `hxy-server/tests/test_technician_profile_v3_contract.py`: real HTTP contract, redaction and own-history behavior.
- `docs/contracts/service-reference-v4.md`, `docs/TEAM-MEMORY.md`, `docs/workstreams/technician.md`: cross-end contract and shared decision records.

---

### Task 1: Lock the v5 handoff payload contract

**Files:**
- Modify: `admin-react/src/technician/serviceReference.ts`
- Modify: `hxy-server/app/api/admin_v2.py`
- Test: `admin-react/tests/technician-minimal-note.test.ts`
- Test: `hxy-server/tests/test_technician_profile_v3_contract.py`

**Interfaces:**
- Produces `buildServiceReferenceV5Payload(userId, selectionSessionId, values)` with optional `profile.technician_observed.service_note` and `recording_outcome`.
- Produces Pydantic fields `ServiceReferenceV5TechnicianObserved.service_note: str` and `recording_outcome: Literal["no_additional_notes"] | None`.

- [ ] **Step 1: Write a frontend failing test for one text-only handoff.**

```ts
it('builds a v5 note as technician context, not customer quote', () => {
  expect(buildServiceReferenceV5Payload(9, 'session-1', {
    serviceNote: '右肩减轻力度后表示合适',
  }).profile.technician_observed).toEqual({
    source: 'technician_observed',
    service_note: '右肩减轻力度后表示合适',
  });
});
```

- [ ] **Step 2: Run the frontend test and confirm it fails because the builder lacks the note contract.**

Run: `npm test -- technician-minimal-note.test.ts`

- [ ] **Step 3: Add `serviceNote` and `recordingOutcome` to `ServiceReferenceInput`; emit trimmed note text only under `technician_observed`; reject no-update mixed with ordinary input.**

```ts
if (values.recordingOutcome && (hasServiceReferenceInput(values) || values.serviceNote?.trim() || values.bodyMapNotes?.length)) {
  throw new Error('本次无补充不能与其他服务内容同时保存');
}
```

- [ ] **Step 4: Run the frontend test and confirm it passes.**

Run: `npm test -- technician-minimal-note.test.ts`

- [ ] **Step 5: Write failing HTTP tests for note-only save, no-update save, mixed no-update rejection, 201-character rejection, phone/diagnostic-text rejection, and no-update customer-confirmation rejection.**

```python
def test_no_additional_notes_cannot_mix_with_note(self, client):
    response = client.post(self.url, json=self.quick_note_payload({
        "recording_outcome": "no_additional_notes", "service_note": "有内容"
    }), headers=self.headers)
    assert response.status_code == 422
```

- [ ] **Step 6: Run those HTTP tests and confirm they fail for missing schema validation.**

Run: `python -m pytest tests/test_technician_profile_v3_contract.py -q`

- [ ] **Step 7: Add fields and a model-level v5 validator. Validate note text with the existing quote safety validator; remove the outcome key before checking all ordinary profile content.**

```python
if self.technician_observed.recording_outcome:
    content = self.model_dump(mode="python")
    content["technician_observed"].pop("recording_outcome", None)
    if ServiceReferenceV5Profile.model_validate(content).has_content():
        raise ValueError("no_additional_notes cannot include service content")
```

- [ ] **Step 8: Run the HTTP contract suite and confirm it passes.**

Run: `python -m pytest tests/test_technician_profile_v3_contract.py -q`

- [ ] **Step 9: Commit the contract slice.**

Run: `git add admin-react/src/technician/serviceReference.ts admin-react/tests/technician-minimal-note.test.ts hxy-server/app/api/admin_v2.py hxy-server/tests/test_technician_profile_v3_contract.py && git commit -m "feat(technician): add handoff note contract"`

### Task 2: Implement the mobile handoff card and writer history

**Files:**
- Modify: `admin-react/src/technician/TechnicianProfileSheet.tsx`
- Modify: `admin-react/src/technician/TechnicianServiceHistoryPage.tsx`
- Modify: `admin-react/src/serviceReferenceDisplay.ts`
- Modify: `hxy-server/app/api/technician.py`
- Test: `admin-react/tests/technician-profile-v3.test.ts`
- Test: `admin-react/tests/technician-workspace.test.ts`
- Test: `hxy-server/tests/test_technician_profile_v3_contract.py`

**Interfaces:**
- Consumes `buildServiceReferenceV5Payload` from Task 1.
- Produces `record_completed: bool`, `recording_outcome: "no_additional_notes" | None`, `service_note: str`, and `own_record_summary: str` only in the writer's service history response.

- [ ] **Step 1: Write a failing component-source test that asserts the card exposes “稍后记录”, a 200-character “还有什么值得下次知道？” input, a no-update action, and no demographic/lifestyle fields.**

```ts
expect(sheet).toContain('还有什么值得下次知道？');
expect(sheet).toContain('本次无新增，完成记录');
expect(sheet).not.toContain('年龄段');
expect(sheet).not.toContain('职业场景');
```

- [ ] **Step 2: Run the focused frontend test and confirm it fails before replacing the old form.**

Run: `npm test -- technician-profile-v3.test.ts`

- [ ] **Step 3: Make the drawer a concise card. Keep service position and project summary visible; make communication/service-adjustment options optional; make the body-map entry collapsed and optional; do not create a confirmation modal.**

```tsx
<Form.Item name="serviceNote" label="还有什么值得下次知道？">
  <Input.TextArea maxLength={200} showCount placeholder="可记来店原因、调整后是否合适、未满足需求或下次要求" />
</Form.Item>
```

- [ ] **Step 4: Preserve failure data and idempotency. Reuse the same key for the exact failed payload; generate a new key only when the payload changes; lock all inputs while saving.**

```tsx
if (lastPayloadSignature.current !== null && lastPayloadSignature.current !== payloadSignature) {
  idempotencyKey.current = crypto.randomUUID();
}
lastValues.current = input;
```

- [ ] **Step 5: Run focused frontend tests and confirm they pass.**

Run: `npm test -- technician-profile-v3.test.ts technician-workspace.test.ts technician-minimal-note.test.ts`

- [ ] **Step 6: Write failing backend tests that a writer sees the note and completion outcome in own history while `_management_profile_record_view` and the safe next-service summary omit note text.**

```python
assert history["service_note"] == "顾客希望安静休息"
assert "顾客希望安静休息" not in json.dumps(_management_profile_record_view(record, db))
```

- [ ] **Step 7: Run the backend test and confirm it fails because history does not project the writer-only fields.**

Run: `python -m pytest tests/test_technician_profile_v3_contract.py -q`

- [ ] **Step 8: Add an own-record query filtered to the current technician, store and completed service. Project only safe completion state and note text; do not alter `_history_profile_summary`, which feeds cross-technician safe summaries.**

```python
"record_completed": bool(own_record),
"recording_outcome": "no_additional_notes" if own_observed.get("recording_outcome") == "no_additional_notes" else None,
"service_note": service_note,
```

- [ ] **Step 9: Map only `no_additional_notes` to a Chinese completion label in display helpers and render note text only in the writer history page.**

- [ ] **Step 10: Run focused backend and frontend tests and confirm they pass.**

Run: `python -m pytest tests/test_technician_profile_v3_contract.py -q && npm test -- technician-profile-v3.test.ts technician-workspace.test.ts technician-minimal-note.test.ts`

- [ ] **Step 11: Commit the user-interface and reader slice.**

Run: `git add admin-react/src/technician/TechnicianProfileSheet.tsx admin-react/src/technician/TechnicianServiceHistoryPage.tsx admin-react/src/serviceReferenceDisplay.ts admin-react/tests/technician-profile-v3.test.ts admin-react/tests/technician-workspace.test.ts hxy-server/app/api/technician.py hxy-server/tests/test_technician_profile_v3_contract.py && git commit -m "feat(technician): streamline service handoff card"`

### Task 3: Update shared contract documents and verify release readiness

**Files:**
- Modify: `docs/contracts/service-reference-v4.md`
- Modify: `docs/TEAM-MEMORY.md`
- Modify: `docs/workstreams/technician.md`
- Modify: `docs/superpowers/plans/2026-09-08-technician-service-handoff-card.md`

**Interfaces:**
- Documents the v5 note/outcome contract delivered by Task 1 and reader boundaries delivered by Task 2.

- [ ] **Step 1: Update the v5 contract with exact fields, visibility, no-update exclusivity and no automatic profile/marketing/algorithm use.**

- [ ] **Step 2: Update shared memory and the technician workstream as local implementation facts only; do not claim merged or released status.**

- [ ] **Step 3: Run contract and regression suites.**

Run: `python -m pytest tests/test_technician_profile_v3_contract.py tests/test_technician_profile_quick_note_contract.py tests/test_customer_profile_records_api.py tests/test_customer_profile_projection.py tests/test_technician_portal_api.py -q`

Run: `npm test -- --runInBand`

- [ ] **Step 4: Build the technician/admin frontend.**

Run: `npm run build`

- [ ] **Step 5: Run whitespace and diff review checks.**

Run: `git diff --check && git diff --stat origin/main...HEAD && git status --short`

- [ ] **Step 6: Commit documentation and plan status.**

Run: `git add docs/contracts/service-reference-v4.md docs/TEAM-MEMORY.md docs/workstreams/technician.md docs/superpowers/plans/2026-09-08-technician-service-handoff-card.md && git commit -m "docs(technician): record handoff card contract"`

## Self-Review

- Spec scope is covered by Task 1 (data and validation), Task 2 (writing and reading UX), and Task 3 (contract, shared memory, automated checks).
- The plan deliberately excludes AI, demographic/lifestyle collection, price/marketing use, body-map redesign and unattended store-manager notifications.
- All names use the v5 contract fields: `service_note`, `recording_outcome`, `record_completed`, and `own_record_summary`.
- Human mobile field acceptance and actual production release are intentionally after local verification and PR merge; neither is claimed by this plan.
