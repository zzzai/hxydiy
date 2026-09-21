# Admin Workspace and Catalog UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the chain-brand admin experience: automatic entry for one workspace, explicit selection for multiple workspaces, persistent workspace switching, auditable account assignments, headquarters template/price-policy editing, and store-level publication/price override editing.

**Architecture:** Authentication storage distinguishes selector credentials from scoped access credentials. A pure workspace model decides routing and labels; React pages render headquarters or store capabilities from the selected server-issued context. Headquarters and store project screens consume the PR 2 APIs and generated OpenAPI types rather than deriving permissions from legacy `Staff.role + store_id` combinations.

**Tech Stack:** React 18, TypeScript 5.6, Ant Design, Refine, Axios, Node test runner, generated OpenAPI types, Vite, Playwright for browser acceptance.

## Delivery Boundary

- This is PR 3 of 3 and starts only after the access-scope and catalog/pricing PRs are merged.
- Do not duplicate authorization rules in labels or route names; the API remains authoritative and the UI only hides unavailable actions for clarity.
- One workspace enters directly. Two or more workspaces show a selector after password verification. The current workspace is always visible and switchable in the header.
- The migrated `admin` account initially has one brand workspace, so it enters headquarters directly until store grants are added.
- Technician mobile login/storage behavior must remain unchanged.
- Use only generated OpenAPI DTOs at API boundaries; local view models may add presentation fields but must not redefine server payloads.

---

### Task 1: Add typed workspace session state and routing decisions

**Files:**
- Create: `admin-react/src/core/auth/workspaceSession.ts`
- Modify: `admin-react/src/core/auth/index.ts`
- Modify: `admin-react/src/api.ts`
- Modify: `admin-react/src/auth.ts`
- Create: `admin-react/tests/workspace-session.test.ts`
- Modify: `admin-react/tests/auth.test.ts`

**Interfaces:**
- Storage keys: scoped admin token, selector token, staff snapshot, active workspace, available workspaces.
- `resolveLoginDestination(workspaces) -> 'denied' | 'app' | 'workspace-select'`
- `saveScopedSession(response)`, `clearAdminSession()`, `getActiveWorkspace()`
- `hasCapability(workspace, capability)` replaces new uses of `canManageStoreMasterData`, including the distinction between managing brand-admin grants and managing non-brand grants.

- [ ] Write failing pure tests for zero/one/multiple workspace routing, corrupted storage, logout cleanup, brand/store labels, and capability mapping for all four roles.
- [ ] Run `npm test --prefix admin-react -- --test-name-pattern=workspace` and confirm missing module/functions are the failures.
- [ ] Implement the typed session helpers using generated login/workspace schemas. Keep legacy storage reads only as a one-release migration path.
- [ ] Update Axios to send only a scoped access token to normal APIs and only the selector token to workspace selection.
- [ ] Run workspace/auth tests and commit with `feat(admin): add workspace session model`.

### Task 2: Implement login selection and in-app workspace switching

**Files:**
- Modify: `admin-react/src/pages/LoginPage.tsx`
- Create: `admin-react/src/pages/WorkspaceSelectPage.tsx`
- Create: `admin-react/src/pages/workspace-select-model.ts`
- Modify: `admin-react/src/App.tsx`
- Modify: `admin-react/src/layouts/MainLayout.tsx`
- Modify: `admin-react/src/core/navigation/index.ts`
- Create: `admin-react/tests/workspace-select-model.test.ts`
- Modify: `admin-react/tests/navigation-registry.test.ts`
- Modify: `admin-react/tests/navigation-boundary.test.ts`

**Interfaces:**
- Login automatically stores and enters a single returned workspace.
- Multiple workspaces route to `/select-workspace` and display role, scope name, and headquarters/store distinction.
- Header workspace switcher reuses the selector flow without asking for the password again while the selector token is valid; expiry returns to login with a clear message.

- [ ] Add failing model/static tests for auto-entry, selector rendering, active workspace header copy, switch behavior, expired selector handling, and prohibition on store/HQ guessing from the username.
- [ ] Implement the selector route and login branching. Do not show the selector for exactly one workspace.
- [ ] Add a compact header switcher that lists only server-returned workspaces and reloads scoped navigation/data after selection.
- [ ] Verify technician routes do not import or clear the new admin selector/session keys unexpectedly.
- [ ] Run focused navigation tests, the full admin test suite, and commit with `feat(admin): select and switch workspaces`.

### Task 3: Replace account role editing with assignment management

**Files:**
- Modify: `admin-react/src/pages/StaffAccountsPage.tsx`
- Modify: `admin-react/src/pages/staff-accounts-page-model.ts`
- Create: `admin-react/src/components/staff/AssignmentEditor.tsx`
- Modify: `admin-react/tests/staff-accounts-page-model.test.ts`
- Create: `admin-react/tests/staff-assignment-model.test.ts`

**Interfaces:**
- Account form owns identity/status/password only.
- Assignment editor separately adds/disables `brand_admin`, `hq_operator`, `store_manager`, and `store_staff` grants with brand/store scope validation.
- UI prevents submitting an invalid role/scope combination and displays server errors for duplicate and last-brand-admin rules.

- [ ] Add failing tests for role labels, legal scope options, separate account/assignment payloads, disabled-grant display, duplicate prevention, and last-brand-admin error mapping.
- [ ] Remove legacy manager/staff role mutation from the account form and add the assignment editor using generated DTOs.
- [ ] Show full assignment controls in a `brand_admin` workspace; in an `hq_operator` workspace allow only non-brand grant controls and make the brand-admin restriction explicit; store workspaces remain read-only where the API permits visibility.
- [ ] Run staff account/assignment tests and commit with `feat(admin): manage staff workspace assignments`.

### Task 4: Build the headquarters project template and price-policy screen

**Files:**
- Create: `admin-react/src/pages/BrandProjectsPage.tsx`
- Create: `admin-react/src/pages/brand-projects-page-model.ts`
- Reuse/Modify: `admin-react/src/components/project-options/ProjectBasicFields.tsx`
- Create: `admin-react/src/components/projects/PricePolicyEditor.tsx`
- Modify: `admin-react/src/layouts/MainLayout.tsx`
- Create: `admin-react/tests/brand-projects-page-model.test.ts`
- Modify: `admin-react/tests/project-content.test.ts`

**Interfaces:**
- Headquarters page edits shared template content and `store/group/member` policies and displays per-store distribution/publication/effective-price status.
- Fixed policy disables store override; bounded policy requires inclusive min/max; open policy permits non-negative store override.
- `brand_admin` and `hq_operator` see allowed write actions; store roles cannot route to the page.

- [ ] Add failing pure tests for template payloads, price-unit conversion, all policy modes, invalid bounds, unchanged-field omission, and role capability display.
- [ ] Implement the headquarters list/editor and store-distribution view using generated template/policy DTOs and existing field components where their semantics match.
- [ ] Add clear copy distinguishing “总部指导价/总部统一价/门店可调整范围”; never label an override as a new project price history record.
- [ ] Run focused project-content/model tests and commit with `feat(admin): edit brand project templates`.

### Task 5: Build the store publication and price-override screen

**Files:**
- Modify: `admin-react/src/pages/ProjectsPage.tsx`
- Modify: `admin-react/src/pages/projects-page-model.ts`
- Modify: `admin-react/src/components/project-options/CatalogPublishPanel.tsx`
- Create: `admin-react/src/components/projects/StorePriceOverrideEditor.tsx`
- Modify: `admin-react/tests/projects-page-model.test.ts`
- Modify: `admin-react/tests/catalog-options.test.ts`

**Interfaces:**
- Store page shows template content read-only, current effective price, source, policy/range, publication state, and permitted override action.
- Store manager may publish/unpublish and create/remove valid overrides for the active store only.
- Store staff is read-only and sees a plain-language permission explanation. Fixed policy has no editable price control and explains that headquarters has locked the price.

- [ ] Add failing tests for effective-price/source presentation, fixed/bounded/open controls, reset-to-headquarters action, cents conversion, store-manager actions, and store-staff read-only behavior with an explicit denial reason.
- [ ] Refactor the existing project page to call store project endpoints when active scope is `store`; remove legacy role/store inference from new behavior.
- [ ] Preserve existing option/catalog functionality and publication confirmation flows; only change controls whose ownership moved to headquarters or store pricing.
- [ ] Run project/catalog-option tests and commit with `feat(admin): edit store project price overrides`.

### Task 6: Regenerate contracts and run browser acceptance

**Files:**
- Modify: `admin-react/src/generated/openapi.d.ts`
- Modify if generated by the existing command: `hxy-server/openapi.json`
- Modify: `docs/CONTROL-BOARD.md`
- Modify: `docs/CURRENT-STATE.md` and `docs/WORK-STATUS.md` only in the window that actually verifies production deployment.
- Create at execution time: Playwright screenshots/traces under the repository's ignored test-output location.

- [ ] Run `npm run generate:contracts --prefix admin-react` and assert `git diff` contains only expected API type changes.
- [ ] Run `npm test --prefix admin-react`, `npm run build --prefix admin-react`, `python -m unittest discover -s tests -p 'test_*.py'`, and `git diff --check`.
- [ ] Run affected backend auth/catalog/Schemathesis tests to prove the UI PR did not drift from the merged API contract.
- [ ] With an isolated local database, use Playwright to verify: single brand workspace auto-entry; multiple workspace selection; header switch; brand template edit; fixed/bounded/open policy forms; store publication; valid override; invalid override rejection; reset to headquarters price; store-staff read-only; logout/login restoration.
- [ ] After all three PRs merge, run the protected deployment script with database backup and migration preflight. Verify production health, login, workspace selection, role isolation, project count, and zero price drift before updating current-state documents.
- [ ] Record real browser checks separately from WeChat/device/store field acceptance; do not claim field acceptance from CI, HTTP 200, or desktop Playwright alone.
