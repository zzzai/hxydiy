# Auxiliary menu visibility migration

Updated: 2026-09-24

The approved additive migration `20260924_aux_menu_visibility.py` adds
`projects.independently_visible` as non-null with a true server default. It
does not hide any existing project during migration. The separate, store-1-only
reconciliation applies the six-item auxiliary menu after application deployment.

Before release, create a `pg_dump -Fc` backup, verify its SHA-256 checksum,
restore it into an isolated database, and run `alembic upgrade head` there.
Verify revision `20260924_aux_visibility`, existing project counts, and that
all existing projects default to visible. Only then migrate production. The
release script permits this one new migration and still blocks unknown or
removed migrations.

After deployment, run `python scripts/reconcile_aux_menu.py --store-id 1`
without `--apply` and inspect its plan. Apply only if the six old project
codes, prices, and states match the expected preflight. After `--apply`, verify
the six public standalone items and their order/prices, hidden old projects'
detail and linked-choice access, immutable historical selection snapshots, and
an idempotent second dry-run.

Application rollback retains the additive column. Do not automatically
downgrade after menu writes: downgrade drops the visibility flag and would
expose the legacy items again. Reversal of operational menu changes requires
new audited price/catalog versions, not editing old snapshots.
