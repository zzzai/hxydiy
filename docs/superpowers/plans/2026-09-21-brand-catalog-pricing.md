# Brand Catalog and Store Pricing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce headquarters-owned project templates and explicit store price policies/overrides without changing current project IDs, customer-visible prices, order history, or store publication behavior.

**Architecture:** A brand project template owns shared descriptive content. Existing `Project` rows remain store-level operational instances and gain a template link. Headquarters price policies define defaults and override constraints; store override rows record approved deviations. One pricing resolver becomes the source for admin display, public catalog, membership selection, and order creation.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL, Pydantic v2, pytest, Schemathesis, OpenAPI.

## Delivery Boundary

- This is PR 2 of 3 and starts only after the access-scope PR is merged.
- Use `StaffContext` role/scope checks from PR 1; do not recreate permission logic in catalog endpoints.
- Preserve every existing `Project.id`, project code, publication state, `PriceBook` history, order line, selection record, and customer-visible effective price.
- Headquarters owns template content and policy. Store manager owns only store publication and permitted store price overrides. Store staff is read-only.
- Supported price types remain `store`, `group`, and `member`.
- A policy mode is one of `fixed`, `bounded_override`, or `open_override`: `fixed` is the forced headquarters price, while the two override modes explicitly permit store overrides. Bounds use integer cents and cannot be negative.
- Update business implementation, OpenAPI, contract tests, `docs/contracts/`, and `docs/TEAM-MEMORY.md` in the same PR.

---

### Task 1: Add brand template and pricing-policy persistence

**Files:**
- Modify: `hxy-server/app/models/catalog.py`
- Modify: `hxy-server/app/models/__init__.py`
- Create: `hxy-server/alembic/versions/20260921_brand_project_pricing.py`
- Create: `hxy-server/tests/test_brand_catalog_migration.py`
- Modify: `hxy-server/tests/test_alembic_contract.py`
- Modify: `hxy-server/tests/test_release_scripts.py`
- Modify: affected migration allowlists under `tools/release/`

**Interfaces:**
- `BrandProjectTemplate`: brand code, name, category, duration, description/content fields, status, timestamps.
- `Project.brand_template_id`: non-null after backfill; existing `Project` remains the store instance.
- `BrandProjectPricePolicy`: template, price type, default amount, mode, optional min/max, status, timestamps.
- `StoreProjectPriceOverride`: project, price type, amount, status, actor, timestamps.

- [ ] Add a failing migration test from the current schema that snapshots all project IDs/codes/publication states and active `PriceBook` amounts, upgrades, and proves there is one template per existing logical project, every store project is linked, and effective prices are byte-for-byte equivalent.
- [ ] Add constraint tests for unique template code, one active policy per template/type, one active override per project/type, valid price types, non-negative cents, and ordered min/max bounds.
- [ ] Run `python -m pytest hxy-server/tests/test_brand_catalog_migration.py hxy-server/tests/test_alembic_contract.py -q` and confirm the schema is the only missing dependency.
- [ ] Implement the models and migration. Seed template/policy data from current project and latest active `PriceBook` rows; do not rewrite or delete price history.
- [ ] Add migration release validation and one-head assertions, re-run focused tests, and commit with `feat(catalog): add brand templates and price policies`.

### Task 2: Build one deterministic effective-price resolver

**Files:**
- Create: `hxy-server/app/domain/brand_pricing.py`
- Modify: `hxy-server/app/domain/membership_pricing.py`
- Modify: `hxy-server/app/api/catalog.py`
- Modify: `hxy-server/app/api/orders.py`
- Modify: `hxy-server/app/api/admin_v2.py`
- Create: `hxy-server/tests/test_brand_project_pricing.py`
- Modify: `hxy-server/tests/test_membership_pricing.py`
- Modify: `hxy-server/tests/test_selection_pricing.py`
- Modify: `hxy-server/tests/test_customer_order_cancel.py`

**Interfaces:**
- `EffectiveProjectPrice(price_type, amount_cents, source, policy_id, override_id)`
- `resolve_effective_project_prices(db, project_id, at) -> dict[str, EffectiveProjectPrice]`
- Precedence: active valid store override, then active policy default, then legacy active `PriceBook` fallback during the compatibility window.

- [ ] Add failing table-driven tests for fixed, bounded, open, absent, disabled, expired, below-minimum, above-maximum, and all three price types. Include a regression fixture built from the current 14 production-shaped projects.
- [ ] Add failing integration tests proving public catalog, membership pricing, selection pricing, order creation, and admin listing return the same resolved amount/source.
- [ ] Run the focused pricing tests and confirm failures reveal duplicated legacy `PriceBook` reads.
- [ ] Implement the resolver and replace direct current-price queries in the listed consumers. Keep historical order/selection snapshots immutable.
- [ ] Re-run focused pricing/order tests and commit with `refactor(pricing): centralize effective project prices`.

### Task 3: Add headquarters project-template and policy APIs

**Files:**
- Modify: `hxy-server/app/api/admin_v2.py`
- Create: `hxy-server/app/schemas/brand_catalog.py`
- Create: `hxy-server/tests/test_admin_brand_catalog_api.py`
- Modify: `hxy-server/tests/test_admin_catalog_schemathesis.py`
- Modify: `hxy-server/tests/test_api_contracts.py`

**Interfaces:**
- `GET /api/v1/admin/v2/brand/project-templates`
- `POST /api/v1/admin/v2/brand/project-templates`
- `GET/PATCH /api/v1/admin/v2/brand/project-templates/{template_id}`
- `PUT /api/v1/admin/v2/brand/project-templates/{template_id}/price-policies/{price_type}`
- `GET /api/v1/admin/v2/brand/project-templates/{template_id}/distribution` reports linked stores, publication state, and effective-price source without granting store-operating authority.
- `brand_admin`: full write; `hq_operator`: template/policy write except permission/account administration; store roles: read only through store endpoints.

- [ ] Add failing API tests for strict request schemas, code uniqueness, invalid bounds/modes, partial update semantics, distribution reporting, role matrix, audit events, and pagination.
- [ ] Run the focused tests and verify failures are missing endpoints rather than fixture assumptions.
- [ ] Implement the minimal endpoints with transaction-safe validation and structured audit details.
- [ ] Add explicit OpenAPI operation IDs and response/error schemas; regenerate `hxy-server/openapi.json` and `admin-react/src/generated/openapi.d.ts`.
- [ ] Run the API contracts and scoped Schemathesis cases, then commit with `feat(catalog): manage brand project templates`.

### Task 4: Add store project publication and price-override APIs

**Files:**
- Modify: `hxy-server/app/api/admin_v2.py`
- Modify: `hxy-server/app/schemas/brand_catalog.py`
- Create: `hxy-server/tests/test_admin_store_project_pricing_api.py`
- Modify: `hxy-server/tests/test_admin_audit_store_scope.py`
- Modify: `hxy-server/tests/test_store_isolation_regressions.py`

**Interfaces:**
- `GET /api/v1/admin/v2/store/projects` returns template content, publication state, effective prices, price source, and override eligibility for the selected store context.
- `PATCH /api/v1/admin/v2/store/projects/{project_id}/publication`
- `PUT /api/v1/admin/v2/store/projects/{project_id}/price-overrides/{price_type}`
- `DELETE /api/v1/admin/v2/store/projects/{project_id}/price-overrides/{price_type}` restores policy default.

- [ ] Add failing tests for same-store writes, cross-store denial, fixed-policy denial, bounded validation, removal fallback, disabled templates, store-manager access, store-staff denial, and audit evidence.
- [ ] Run the focused store-pricing/isolation tests and confirm the expected endpoint failures.
- [ ] Implement scoped endpoints using `StaffContext.store_id`; never accept a caller-supplied store ID as authorization.
- [ ] Preserve the legacy project edit endpoints as brand compatibility adapters until PR 3 switches the UI; route their price effects through the resolver and reject store-role master-data writes.
- [ ] Re-run focused tests and commit with `feat(catalog): manage store project overrides`.

### Task 5: Freeze contracts and verify no price drift

**Files:**
- Create: `docs/contracts/brand-project-catalog-and-pricing.md`
- Modify: `docs/TEAM-MEMORY.md`
- Modify: `docs/CONTROL-BOARD.md`
- Modify: `hxy-server/tests/test_final_menu_baseline.py`
- Modify: `hxy-server/tests/test_api_contracts.py`

- [ ] Document ownership, role matrix, policy modes, resolver precedence, publication semantics, audit requirements, compatibility endpoints, and rollback behavior.
- [ ] Add a baseline test that compares all seeded/current project codes and `store/group/member` prices before and after migration/resolution.
- [ ] Run `python -m pytest hxy-server/tests/test_brand_catalog_migration.py hxy-server/tests/test_brand_project_pricing.py hxy-server/tests/test_admin_brand_catalog_api.py hxy-server/tests/test_admin_store_project_pricing_api.py hxy-server/tests/test_membership_pricing.py hxy-server/tests/test_selection_pricing.py hxy-server/tests/test_final_menu_baseline.py hxy-server/tests/test_store_isolation_regressions.py hxy-server/tests/test_api_contracts.py hxy-server/tests/test_admin_catalog_schemathesis.py -q`.
- [ ] Run `python -m unittest discover -s tests -p 'test_*.py'`, `npm test --prefix admin-react`, `npm run build --prefix admin-react`, and `git diff --check`.
- [ ] Produce a read-only migration rehearsal report listing template count, linked-project count, policies, overrides, and every pre/post effective-price difference. The accepted difference count is zero.
- [ ] Confirm the PR description keeps merge, production migration, and store acceptance unclaimed until separately evidenced.
