# Contract Governance and API Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish one lightweight control plane, make the project and product admin API contract machine-readable, generate frontend types from it, and add deterministic Schemathesis validation without duplicating the existing governance system.

**Architecture:** Existing PRDs, versioned contracts, FastAPI schemas, Git history, and release evidence remain authoritative for their respective layers. The new control board tracks only active cross-end flow; FastAPI OpenAPI becomes the machine contract, generated TypeScript types consume that contract, and Schemathesis validates runtime conformance in an isolated test environment.

**Tech Stack:** Markdown, Python 3.12, FastAPI, Pydantic v2, OpenAPI 3.1, TypeScript 5.6, `openapi-typescript`, Schemathesis, GitHub Actions.

## Global Constraints

- Work from an isolated worktree based on verified `origin/main` and preserve unrelated user changes.
- Do not add a full spec-kit installation or a second constitution, PRD, contract, or memory hierarchy.
- Pilot only project and product admin APIs before expanding to other endpoints.
- Do not change price, permission, store-isolation, publication-state, idempotency, audit, or privacy semantics as part of contract hardening.
- Never run generated write cases against production; Schemathesis uses an isolated test database or dedicated non-production server.
- Keep local, PR, merged, deployed, and field-accepted states separate.

---

### Task 1: Add the lightweight control plane

**Files:**
- Create: `docs/CONTROL-BOARD.md`
- Create: `docs/templates/incremental-feature-spec.md`
- Modify: `docs/CONTEXT-MANIFEST.md`
- Modify: `docs/AI-WINDOW-PROMPTS.md`
- Test: `tests/test_project_memory_contract.py`

**Interfaces:**
- Consumes: existing PRDs, contracts, workstreams, `CURRENT-STATE.md`, and Git evidence.
- Produces: Feature ID lifecycle and an incremental specification template without duplicating long-term facts.

- [ ] Add a failing static contract that requires the board, template, total-control prompt, and eight lifecycle states.
- [ ] Run the targeted unittest and confirm it fails because the board is absent.
- [ ] Add the minimal board, template, manifest routing, and total-control prompt.
- [ ] Run `python -m unittest discover -s tests -p 'test_*.py'` and `git diff --check`.
- [ ] Commit with `docs: add incremental feature control plane`.

### Task 2: Freeze the project and product OpenAPI pilot

**Files:**
- Modify: `hxy-server/app/api/admin_v2.py`
- Create or modify: focused schema modules under `hxy-server/app/schemas/`
- Modify: `hxy-server/tests/test_api_contracts.py`
- Modify: affected project/product contract tests
- Create: `tools/openapi/export_openapi.py`
- Create: `tests/test_openapi_generation_contract.py`
- Update: `docs/contracts/` and `docs/TEAM-MEMORY.md` only when the machine contract changes a shared semantic fact.

**Interfaces:**
- Consumes: current project/product FastAPI behavior and existing permission tests.
- Produces: explicit request, response, pagination, error, and authentication schemas for the pilot endpoints plus a deterministic OpenAPI export command.

- [ ] Add failing tests for explicit schemas, security metadata, stable operation identifiers, and deterministic export.
- [ ] Run the focused tests and confirm failures reflect missing OpenAPI metadata rather than changed business behavior.
- [ ] Add the smallest Pydantic response/security metadata needed to match current behavior.
- [ ] Export OpenAPI twice and assert byte-identical output.
- [ ] Run affected backend tests, the full static contracts, and `git diff --check`.

### Task 3: Generate and consume admin TypeScript types

**Files:**
- Modify: `admin-react/package.json`
- Modify: `admin-react/package-lock.json`
- Create: `admin-react/openapi-ts.config.mjs` or an equivalent pinned command configuration
- Create: `admin-react/src/generated/api-schema.d.ts`
- Modify: `admin-react/src/pages/projects-page-model.ts`
- Modify: `admin-react/src/pages/products-page-model.ts`
- Modify: focused page-model tests
- Modify: `.github/workflows/ci.yml`
- Modify: `.github/workflows/trusted-pr-gate.yml`
- Modify: `tests/test_github_automation_contract.py`

**Interfaces:**
- Consumes: the deterministic FastAPI OpenAPI artifact from Task 2.
- Produces: generated project/product DTO types used by current page models and a CI drift check that fails when regeneration changes tracked output.

- [ ] Add failing frontend and workflow contract tests requiring generated DTO imports and CI regeneration.
- [ ] Run the tests and confirm they fail because generation is not configured.
- [ ] Pin `openapi-typescript`, generate the schema types, and replace only project/product duplicate DTOs.
- [ ] Add a non-writing CI check that regenerates and rejects an uncommitted diff.
- [ ] Run admin tests, TypeScript build, static contracts, and `git diff --check`.

### Task 4: Add scoped Schemathesis validation

**Files:**
- Modify: `hxy-server/requirements-dev.txt`
- Create: `hxy-server/schemathesis.toml`
- Create: `hxy-server/tests/test_admin_catalog_schemathesis.py` or a focused equivalent
- Modify: `.github/workflows/ci.yml`
- Modify: `.github/workflows/trusted-pr-gate.yml`
- Modify: `tests/test_github_automation_contract.py`
- Update: `docs/CONTROL-BOARD.md`

**Interfaces:**
- Consumes: the explicit pilot OpenAPI contract and isolated backend test database.
- Produces: reproducible project/product response-conformance and server-error findings, initially report-only and later eligible for a blocking gate.

- [ ] Add failing contract tests requiring a pinned Schemathesis dependency, non-production configuration, and scoped CI command.
- [ ] Run the tests and confirm the integration is missing.
- [ ] Add the minimal in-process or dedicated-test-server setup with seeded roles and stores.
- [ ] Run the scoped suite, classify every finding, and convert confirmed business defects into fixed regression tests.
- [ ] Keep the first CI integration report-only until there are no unclassified failures; record the evidence in the control board.

### Task 5: Converge and hand off

**Files:**
- Modify only the active status and evidence in `docs/CONTROL-BOARD.md`.
- Update `docs/workstreams/admin.md` when the admin pilot is locally complete.
- Update `docs/CURRENT-STATE.md` and `docs/WORK-STATUS.md` only if an actual production deployment occurs.

**Interfaces:**
- Consumes: verified outputs from Tasks 1-4.
- Produces: a precise handoff distinguishing local, PR, merge, deployment, and field acceptance.

- [ ] Compare implementation, OpenAPI, generated types, tests, and the incremental specification for drift.
- [ ] Run all risk-relevant validation once after the final code change.
- [ ] Record exact commands, counts, branch, commit, PR, and any remaining field acceptance.
- [ ] Do not claim deployment or field acceptance without their independent evidence.
