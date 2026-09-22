# Chain Brand Access Scope Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single `Staff.role + Staff.store_id` authorization model with auditable account-role-scope assignments while preserving current admin and technician login behavior until the new workspace UI ships.

**Architecture:** `Staff` remains the login identity. A new `StaffScopeAssignment` records each active brand or store grant. Admin login returns the available workspaces and a short-lived selector token; selecting a workspace issues a scoped access token. Existing admin access tokens remain temporarily accepted during the three-PR rollout, and technician login keeps its current token contract.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Pydantic v2, JWT, pytest, PostgreSQL, OpenAPI.

## Delivery Boundary

- This is PR 1 of 3 and must merge before the catalog/pricing and admin UI PRs.
- Do not add project-template, price-policy, or React workspace UI behavior in this PR.
- Do not remove `Staff.role` or `Staff.store_id`; they remain compatibility fields until all consumers have migrated.
- `brand_admin` and `hq_operator` authorize brand scope only. Store access requires a separate store assignment.
- One active assignment is unique per `(staff_id, role, scope_type, scope_id)`; brand assignments require `scope_id IS NULL`, store assignments require a valid store ID.
- Disabling an account or incrementing `credentials_version` invalidates selector and scoped tokens. Disabling an assignment invalidates tokens bound to it.
- The migrated `admin` account keeps its password hash, changes its legacy compatibility fields to headquarters admin with no fixed store, and increments `credentials_version`; other migrated accounts keep their current credential version.
- Update `docs/contracts/`, `docs/TEAM-MEMORY.md`, generated OpenAPI, and contract tests in the same PR because authentication and permission semantics change.

---

### Task 1: Add assignment persistence and a reversible data migration

**Files:**
- Create: `hxy-server/app/models/staff_access.py`
- Modify: `hxy-server/app/models/core.py`
- Modify: `hxy-server/app/models/__init__.py`
- Create: `hxy-server/alembic/versions/20260921_staff_scope_assignments.py`
- Create: `hxy-server/tests/test_staff_scope_assignment_migration.py`
- Modify: `hxy-server/tests/test_alembic_contract.py`
- Modify: `hxy-server/tests/test_release_scripts.py`
- Modify: affected migration allowlists under `tools/release/`

**Interfaces:**
- `StaffScopeAssignment(staff_id, role, scope_type, scope_id, status, created_by_staff_id, created_at, updated_at)`
- `AuditLog` gains nullable `assignment_id`, `actor_role`, `scope_type`, and `scope_id` fields so writes can retain the active authorization context.
- Roles: `brand_admin | hq_operator | store_manager | store_staff`
- Scope types: `brand | store`
- Statuses: `active | disabled`

- [ ] Add a migration test that upgrades a pre-change database and asserts: the historical headquarters `admin` becomes an active `brand_admin` grant, its password hash is unchanged, its fixed store is cleared, its credential version increments exactly once, existing manager/staff accounts receive equivalent store grants without credential-version changes, technician credentials remain unchanged, duplicates are impossible, and downgrade removes only the new assignment/audit additions.
- [ ] Run `python -m pytest hxy-server/tests/test_staff_scope_assignment_migration.py hxy-server/tests/test_alembic_contract.py -q` and confirm the failure is caused by the missing model/migration.
- [ ] Add the model, constraints, relationships, and migration. Populate grants from legacy fields without changing usernames, password hashes, or project data; apply the credential-version/store cleanup only to the protected `admin` migration case.
- [ ] Add the new migration to release validation/allowlists and assert the Alembic graph still has one head after `20260921_product_catalog_management`.
- [ ] Re-run the focused tests and commit with `feat(auth): add staff scope assignments`.

### Task 2: Centralize workspace resolution and scoped authorization

**Files:**
- Create: `hxy-server/app/domain/staff_workspaces.py`
- Modify: `hxy-server/app/api/admin.py`
- Modify: `hxy-server/app/api/admin_v2.py`
- Create: `hxy-server/tests/test_admin_workspace_authorization.py`
- Modify: `hxy-server/tests/test_auth_boundary_p0.py`
- Modify: `hxy-server/tests/test_store_isolation_regressions.py`

**Interfaces:**
- `WorkspaceGrant`: `assignment_id`, `role`, `scope_type`, `scope_id`, `scope_name`
- `StaffContext`: `staff`, `assignment_id`, `role`, `scope_type`, `store_id`
- `list_staff_workspaces(db, staff) -> list[WorkspaceGrant]`
- `create_workspace_selector_token(staff) -> str`
- `create_scoped_staff_token(staff, assignment) -> str`
- `resolve_staff_context(token, db, allow_legacy=True) -> StaffContext`
- `audit_context(staff_context) -> dict` supplies assignment, role, scope type, scope/store ID to existing audit writers.
- Scoped JWT claims: `token_type=staff_scope`, `assignment_id`, `role`, `scope_type`, `scope_id`, `credentials_version`

- [ ] Write failing tests for brand/store grant resolution, disabled grants, mismatched staff/assignment, missing store, credential-version revocation, store isolation, and rejection of brand-only users from store-scoped operations.
- [ ] Run `python -m pytest hxy-server/tests/test_admin_workspace_authorization.py hxy-server/tests/test_auth_boundary_p0.py hxy-server/tests/test_store_isolation_regressions.py -q` and confirm authorization failures are specific to the missing resolver.
- [ ] Implement the domain resolver and make `_current_staff` expose a `StaffContext` internally while preserving legacy token acceptance for non-revoked existing admin UI sessions during this rollout.
- [ ] Keep `create_staff_token` and technician endpoints behaviorally unchanged; add regression coverage proving technician login and `/api/v1/technician/me` still work.
- [ ] Replace direct headquarters checks in new assignment endpoints with context-based predicates; do not mechanically rewrite unrelated endpoint behavior in this task.
- [ ] Re-run focused authorization and technician tests and commit with `refactor(auth): resolve scoped staff context`.

### Task 3: Add login workspace discovery and selection APIs

**Files:**
- Modify: `hxy-server/app/api/admin.py`
- Create: `hxy-server/app/schemas/staff_access.py`
- Modify: `hxy-server/app/openapi.py`
- Modify: `hxy-server/tests/test_api_contracts.py`
- Modify: `hxy-server/tests/test_admin_workspace_authorization.py`
- Modify: `hxy-server/tests/test_admin_catalog_schemathesis.py`

**Interfaces:**
- `POST /api/v1/admin/login` returns existing `token` and `staff` fields during rollout plus `selector_token` and `workspaces`; when there is exactly one workspace, `token` is already scoped to it.
- `POST /api/v1/admin/workspaces/select` accepts `{ "assignment_id": number }` with a selector token and returns `{ "token", "staff", "workspace" }`.
- Zero active workspaces returns `403` after valid credentials; multiple workspaces never select one implicitly.

- [ ] Add failing HTTP tests for zero, one, and multiple workspace login outcomes and for selecting owned, disabled, missing, and another account's assignments.
- [ ] Add failing OpenAPI assertions for explicit login, workspace, selection request/response, `401`, and `403` schemas.
- [ ] Implement strict Pydantic schemas and the selection endpoint. Make selector tokens short-lived and unusable as normal API access tokens.
- [ ] Regenerate `hxy-server/openapi.json` and `admin-react/src/generated/openapi.d.ts`; reject any unrelated generated-contract drift.
- [ ] Run the focused API tests and Schemathesis pilot, then commit with `feat(auth): add workspace login selection`.

### Task 4: Add headquarters assignment management and audit evidence

**Files:**
- Modify: `hxy-server/app/api/admin_v2.py`
- Modify: `hxy-server/app/schemas/staff_access.py`
- Modify: `hxy-server/tests/test_admin_staff_accounts_api.py`
- Modify: `hxy-server/tests/test_admin_audit_store_scope.py`
- Modify: `hxy-server/tests/test_admin_workspace_authorization.py`
- Create: `docs/contracts/staff-workspace-access.md`
- Modify: `docs/TEAM-MEMORY.md`
- Modify: `docs/CONTROL-BOARD.md`

**Interfaces:**
- `GET /api/v1/admin/v2/staff/accounts/{staff_id}/assignments`
- `POST /api/v1/admin/v2/staff/accounts/{staff_id}/assignments`
- `PATCH /api/v1/admin/v2/staff/accounts/{staff_id}/assignments/{assignment_id}`
- `brand_admin` may manage every role. `hq_operator` may manage `hq_operator`, `store_manager`, and `store_staff` grants but may never grant, modify, or revoke `brand_admin`. Store roles cannot manage grants. The last active brand-admin grant cannot be disabled.

- [ ] Add failing tests for assignment CRUD, duplicate grants, missing stores, cross-account paths, last-brand-admin protection, hq-operator management of non-brand roles, hq-operator denial for brand-admin grants, store-role denial, and audit fields containing actor assignment/role/scope, target account, target grant, and before/after status.
- [ ] Run the focused staff-account and audit tests and confirm failures match the absent endpoints.
- [ ] Implement the minimal endpoints and transaction boundaries. Do not allow account creation to silently invent a default assignment.
- [ ] Document the canonical role/scope matrix, login flow, token compatibility window, revocation rules, and migration behavior in the contract and team memory.
- [ ] Run `python -m pytest hxy-server/tests/test_admin_staff_accounts_api.py hxy-server/tests/test_admin_workspace_authorization.py hxy-server/tests/test_admin_audit_store_scope.py -q` and commit with `feat(auth): manage staff workspace grants`.

### Task 5: Verify PR 1 and prepare protected rollout evidence

**Files:**
- Modify only if required by test evidence: `.github/workflows/ci.yml`, `.github/workflows/trusted-pr-gate.yml`
- Create: `tools/release/reports/` output at execution time; do not commit generated reports unless repository policy requires it.

- [ ] Run `python -m pytest hxy-server/tests/test_staff_scope_assignment_migration.py hxy-server/tests/test_admin_workspace_authorization.py hxy-server/tests/test_admin_staff_accounts_api.py hxy-server/tests/test_auth_boundary_p0.py hxy-server/tests/test_store_isolation_regressions.py hxy-server/tests/test_technician_account_lifecycle.py hxy-server/tests/test_api_contracts.py hxy-server/tests/test_admin_catalog_schemathesis.py -q`.
- [ ] Run `python -m unittest discover -s tests -p 'test_*.py'`, `npm test --prefix admin-react`, `npm run build --prefix admin-react`, and `git diff --check`.
- [ ] Export production migration preflight evidence: current Alembic revision, account/grant migration counts, protected admin username, and backup/restore command path. Do not execute the production migration in this PR task.
- [ ] Confirm the PR description separates local verification, PR checks, merge state, production migration, and field acceptance.
