# Catalog options / pricing production-upgrade final fix report

## Scope and execution boundary

- Branch baseline: `506ef38`.
- This change implements the catalog-option, pricing, migration, membership, and confirmation-snapshot requirements in the 2026-08-15 plan and final review.
- No production database migration, deployment, payment workflow, service-ledger expansion, offline settlement, H5 UI, or admin UI was executed or added.
- The local Alembic contract was tested only against disposable SQLite databases.

## Fixes by plan section

### 1. Catalog serialization, immutable published graphs, and monotonic versions

- Catalog draft writes and publication use the shared catalog project-lock protocol, re-read state after acquisition, and keep copy-on-write under the same coordination boundary.
- The schema permits at most one draft and one published catalog version per project. Publication is monotonic and fails if a stale draft could replace a newer publication.
- Published and superseded graphs carry a deterministic snapshot hash. Customer reads and copy-on-write verify it and fail closed on drift.
- Red-to-green coverage includes stale publication, concurrent write-path locking, published-graph drift, and migration-session flush visibility.

### 2. Strict project CRUD and current-published pointer ownership

- Project create/update requests use strict Pydantic models, explicit fields, strict price types, and non-negative `store/group/member` prices.
- Published linked targets cannot be renamed, archived, or deactivated while referenced by a published catalog; duplicate creates a draft and copies the frozen graph.
- `projects.current_published_version_id` is protected by a composite FK `(project.id, current_published_version_id) -> (catalog_version.project_id, catalog_version.id)`, backed by a unique constraint. A project cannot point at another project's version.
- The pointer ownership test was RED before the composite constraint and GREEN afterward; the Alembic upgrade contract also verifies this invariant.

### 3. Strict option combinations

- The create, final-patch, publication, migration, and pricing-resolver paths consistently enforce: preference/free has no linked project or prices; linked/inherit has a linked project and no local prices; dedicated/custom has no link and requires a current store price.
- Unknown and mixed combinations fail instead of falling through a permissive resolver branch.

### 4. Authoritative catalog price output

- Customer catalog output uses authoritative current price bands and returns an explicit `price_source` for free, linked, and custom choices.
- Project price selection is deterministic: latest `published_at`, then `id`, per price type. The admin project list preserves the first row from that order, preventing an old price from overwriting the latest price.
- The ordering regression was RED with `6900` returned instead of `7900`, then GREEN with the ordered query plus `setdefault` map behavior.

### 5. Linked formal project leaves and pinned snapshots

- Published projects without an option catalog remain valid linked leaves when they have a store price.
- A parent publication pins the linked target's catalog version. Customer reads resolve that pinned version (including superseded versions), return its frozen nested snapshot, and reject hash drift or cycles with 409.

### 6. Price database and publication constraints

- Model and Alembic checks reject negative `PriceBook`/option amounts and invalid option-price intervals.
- Publication validation rejects overlapping current option-price intervals and malformed prices.
- The migration audits unsafe Addon price states, including an enabled member price whose amount is missing, instead of silently creating an ambiguous choice.

### 7. Foot-bath promotion: independent confirmed units only

- Pricing counts one unit per confirmed service line (or one compatibility input row), never expands a quantity into multiple promotional units, and requires distinct normalized local parts for repeated local-project units.
- Submission remains a draft/submitted quotation with no foot-bath adjustment. Front-desk confirmation marks the independent rows as confirmed, records service-line provenance when a revision exists, and refreshes the frozen price snapshot.
- The API regression was RED with no post-confirmation adjustment and GREEN with `-3990` after confirmation; non-confirmed submissions remain at `0`.

### 8. Annual membership cycles and expiry

- Membership updates now require strict annual-cycle input: stable cycle id, timezone-aware start/end, expiry, and valid cancellation/renewal transitions.
- A cycle has at most one benefit grant; same-cycle retries must retain its original start, expiry, and membership type.
- Pricing receives member type and expiry. An expired membership, or an old annual record with no expiry, falls back to store price rather than receiving perpetual member pricing.
- The sync/login regression now explicitly verifies that an annual member without expiry remains on store price.

### 9. Migration safety and dry-run/apply equivalence

- The catalog migration is read-only by default and for `--dry-run`; `--apply` refuses non-local targets and redacts target details in its error.
- Dry-run predicts the same copy-on-write graph, deterministic collisions, price replacements, and warnings as apply. Apply flushes before a refresh so a caller using `autoflush=False` cannot lose newly created `diy_options`.
- Legacy source identities are stable across reordering; malformed/non-numeric legacy price inputs and unsafe Addon price states are audited rather than guessed.

## Schema and API contract changes

- Catalog schema: partial active-version uniqueness; composite current-version ownership FK; linked pinned-version FK; price amount and interval checks.
- Membership schema: cycle identifiers and unique grants by `(user_id, membership_cycle_id)`.
- API behavior: strict project and membership payloads; published projects and linked leaves require an authoritative store price; customer catalog prices include source metadata; pinned linked snapshots are immutable/fail-closed.

## RED-to-GREEN evidence

Focused regressions were first observed or introduced as failing cases, then made green. Examples include:

- same annual cycle accepting a changed start time;
- dry-run under-predicting COW code/price warnings;
- five existing-draft catalog write paths bypassing the shared lock;
- parent catalog reads following a later target catalog instead of its pinned version;
- a cross-project `current_published_version_id` being accepted;
- an old row replacing the latest admin project price;
- a confirmed foot-bath combination retaining a zero adjustment;
- an annual member without expiry receiving member price;
- published test fixtures lacking the now-required snapshot hash or linked-leaf store price.

All corresponding focused tests are green in the verification runs below.

## Verification

The execution environment ends individual terminal calls at about 30 seconds, so the full `tests/` collection was run in complete module partitions after the final source changes.

- Catalog model/domain/admin API: `54 passed, 1 warning, 2 subtests passed`.
- Catalog migration: three partitions, `6 + 6 + 6 passed`.
- Alembic contract: `3 passed`.
- Pricing, membership, selection, and admin/API contracts: `81 passed, 1 warning, 12 subtests passed`.
- Auth, closure, content, coupon, customer, DIY, and H5 APIs: `62 passed, 1 warning, 2 subtests passed`.
- Membership sync, occupancy, order/coupon lifecycle, page content, setup, and tracking: `40 passed, 2 failed, 1 warning, 2 subtests passed`.
- Release checks and selection-closure flow: `27 passed, 5 failed, 1 warning, 6 subtests passed`.
- `python -m py_compile` over every changed application/model/domain/migration module: passed.
- `git diff --check`: passed.

Aggregate result: `285 passed, 7 failed, 1 warning, 24 subtests passed`.

The seven failures are pre-existing environment/layout exclusions, not task regressions:

1. `tests/test_setup_admin.py` and `tests/test_setup_staff.py`: Windows does not expose the POSIX `chmod(0600)` mode asserted by these tests.
2. `tests/test_release_layout.py` (2) and `tests/test_release_scripts.py` (3): their repository-root calculation expects a non-worktree production/release layout and POSIX shell paths; it resolves to `...\.worktrees\deploy` / `...\.worktrees\hxy-server`, which do not exist in this checkout.

The only recurring warning is the existing Starlette `TestClient`/httpx deprecation warning.

## Residual risks and gates

- Before production use, rehearse the full Alembic chain and PostgreSQL restore/migration path; this work intentionally did not execute it.
- Customer catalog reads still have an N+1 query shape and should be profiled before high-volume release.
- The later service-ledger/settlement work must freeze confirmed timestamps, rule/catalog/price versions, and redemption state inside its own transaction; it remains deliberately outside this change.
