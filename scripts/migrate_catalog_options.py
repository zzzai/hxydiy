"""Migrate one store's legacy DIY options and attached addons into a draft catalog.

The command is read-only unless ``--apply`` is supplied explicitly. Migrated
drafts remain unpublished so staff can review them before customer exposure.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Iterable

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.domain.catalog_options import copy_catalog_version_graph
from app.models import (
    Addon,
    OptionChoicePrice,
    Project,
    ProjectCatalogVersion,
    ProjectOptionChoice,
    ProjectOptionGroup,
    Store,
)


@dataclass
class MigrationReport:
    created_versions: int = 0
    created_groups: int = 0
    created_choices: int = 0
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _ChoiceSpec:
    source_key: str
    code: str
    name: str
    choice_type: str
    charge_mode: str
    prices: tuple[tuple[str, int], ...] = ()


@dataclass(frozen=True)
class _GroupSpec:
    code: str
    name: str
    choices: tuple[_ChoiceSpec, ...]


def _stable_code(prefix: str, source: str, index: int | None = None) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", source.lower()).strip("-")
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()[:8]
    ordinal = f"-{index + 1}" if index is not None else ""
    suffix = slug or digest
    available = 32 - len(prefix) - len(ordinal) - 1
    if len(suffix) > available:
        suffix = f"{suffix[: max(1, available - 9)]}-{digest}"
    return f"{prefix}-{suffix}{ordinal}"[:32]


def _legacy_specs(project: Project, warnings: list[str]) -> tuple[_ChoiceSpec, ...]:
    result: list[_ChoiceSpec] = []
    occurrences: dict[str, int] = {}
    options = project.diy_options if isinstance(project.diy_options, list) else []
    if project.diy_options and not isinstance(project.diy_options, list):
        warnings.append(f"project {project.code}: diy_options is not a list; skipped")
        return ()
    for index, option in enumerate(options):
        if not isinstance(option, dict) or not str(option.get("label", "")).strip():
            warnings.append(f"project {project.code}: invalid diy_options entry at index {index}; skipped")
            continue
        label = str(option["label"]).strip()
        normalized_label = " ".join(label.split()).casefold()
        occurrence = occurrences.get(normalized_label, 0)
        occurrences[normalized_label] = occurrence + 1
        amount = option.get("price_cents")
        if isinstance(amount, (int, float)) and not isinstance(amount, bool) and amount != 0:
            warnings.append(
                f"project {project.code} legacy option {label}: non-zero price_cents={amount} ignored"
            )
        source_key = f"legacy:{normalized_label}:{occurrence + 1}"
        result.append(_ChoiceSpec(
            source_key=source_key,
            code=_stable_code("legacy", normalized_label, occurrence),
            name=label,
            choice_type="preference",
            charge_mode="free",
        ))
    return tuple(result)


def _addon_spec(addon: Addon) -> _ChoiceSpec:
    if not addon.chargeable:
        return _ChoiceSpec(
            source_key=f"addon:{addon.code}",
            code=_stable_code("addon", addon.code),
            name=addon.name,
            choice_type="preference",
            charge_mode="free",
        )
    store_amount = addon.store_price_cents
    if store_amount is None:
        store_amount = addon.price_cents
    prices: list[tuple[str, int]] = [("store", int(store_amount))]
    if addon.member_price_enabled and addon.member_price_cents is not None:
        prices.append(("member", int(addon.member_price_cents)))
    return _ChoiceSpec(
        source_key=f"addon:{addon.code}",
        code=_stable_code("addon", addon.code),
        name=addon.name,
        choice_type="dedicated_charge",
        charge_mode="custom_price",
        prices=tuple(prices),
    )


def _collect_addons(
    db: Session,
    store_id: int,
    warnings: list[str],
) -> dict[int, list[Addon]]:
    by_project: dict[int, list[Addon]] = {}
    addons = list(db.scalars(
        select(Addon).where(Addon.store_id == store_id).order_by(Addon.display_order, Addon.id)
    ))
    for addon in addons:
        if addon.parent_project_id is None:
            continue
        parent = db.get(Project, addon.parent_project_id)
        if parent is None:
            warnings.append(f"addon {addon.code}: parent project {addon.parent_project_id} is missing; skipped")
            continue
        if parent.store_id != store_id:
            warnings.append(f"addon {addon.code}: parent project belongs to another store; skipped")
            continue
        by_project.setdefault(parent.id, []).append(addon)
    return by_project


def _group_specs(project: Project, addons: Iterable[Addon], warnings: list[str]) -> tuple[_GroupSpec, ...]:
    specs: list[_GroupSpec] = []
    legacy = _legacy_specs(project, warnings)
    if legacy:
        specs.append(_GroupSpec(code="legacy-diy-options", name="旧 DIY 选项（待审核）", choices=legacy))
    addon_choices = tuple(_addon_spec(addon) for addon in addons)
    if addon_choices:
        specs.append(_GroupSpec(code="legacy-addons", name="旧加项（待审核）", choices=addon_choices))
    return tuple(specs)


def _latest_draft(db: Session, project_id: int) -> ProjectCatalogVersion | None:
    return db.scalar(
        select(ProjectCatalogVersion)
        .where(
            ProjectCatalogVersion.project_id == project_id,
            ProjectCatalogVersion.status == "draft",
        )
        .order_by(ProjectCatalogVersion.version.desc(), ProjectCatalogVersion.id.desc())
        .limit(1)
    )


def _next_version(db: Session, project_id: int) -> int:
    current = db.scalar(select(func.max(ProjectCatalogVersion.version)).where(
        ProjectCatalogVersion.project_id == project_id
    ))
    return int(current or 0) + 1


def _matching_group(
    db: Session,
    version_id: int,
    spec: _GroupSpec,
    warnings: list[str],
) -> tuple[ProjectOptionGroup | None, str]:
    base = spec.code
    for attempt in range(100):
        code = base if attempt == 0 else _stable_code(base[:14], f"{spec.name}:{attempt}")
        group = db.scalar(select(ProjectOptionGroup).where(
            ProjectOptionGroup.catalog_version_id == version_id,
            ProjectOptionGroup.code == code,
        ))
        if group is None or group.name == spec.name:
            if attempt:
                warnings.append(f"catalog version {version_id}: group code {base} conflicted; using {code}")
            return group, code
    raise RuntimeError(f"cannot allocate a stable group code for {spec.name}")


def _choice_matches(choice: ProjectOptionChoice, spec: _ChoiceSpec) -> bool:
    return (
        choice.name == spec.name
        and choice.choice_type == spec.choice_type
        and choice.charge_mode == spec.charge_mode
    )


def _matching_choice(
    db: Session,
    group_id: int,
    spec: _ChoiceSpec,
    warnings: list[str],
) -> tuple[ProjectOptionChoice | None, str]:
    base = spec.code
    for attempt in range(100):
        code = base if attempt == 0 else _stable_code(base[:14], f"{spec.source_key}:{attempt}")
        choice = db.scalar(select(ProjectOptionChoice).where(
            ProjectOptionChoice.option_group_id == group_id,
            ProjectOptionChoice.code == code,
        ))
        if choice is None or _choice_matches(choice, spec):
            if attempt:
                warnings.append(f"option group {group_id}: choice code {base} conflicted; using {code}")
            return choice, code
    raise RuntimeError(f"cannot allocate a stable choice code for {spec.name}")


def _reconcile_current_prices(
    db: Session,
    choice: ProjectOptionChoice,
    spec: _ChoiceSpec,
    effective_at: datetime,
    warnings: list[str],
) -> None:
    added = False
    changed = False
    for price_type, amount_cents in spec.prices:
        current = list(db.scalars(
            select(OptionChoicePrice)
            .where(
                OptionChoicePrice.option_choice_id == choice.id,
                OptionChoicePrice.price_type == price_type,
                OptionChoicePrice.effective_from <= effective_at,
                or_(OptionChoicePrice.effective_to.is_(None), OptionChoicePrice.effective_to > effective_at),
            )
            .order_by(OptionChoicePrice.effective_from.desc(), OptionChoicePrice.id.desc())
        ))
        matching = next((price for price in current if price.amount_cents == amount_cents), None)
        conflicts = [price for price in current if price.amount_cents != amount_cents]
        if conflicts:
            old_amounts = sorted({price.amount_cents for price in conflicts})
            for price in conflicts:
                price.effective_to = effective_at
            changed = True
            warnings.append(
                f"option {choice.name} {price_type} current price {old_amounts} replaced with {amount_cents}"
            )
        if matching is None:
            db.add(OptionChoicePrice(
                option_choice_id=choice.id,
                price_type=price_type,
                amount_cents=amount_cents,
                effective_from=effective_at,
            ))
            added = True
    if added or changed:
        db.flush()


def _predict_group_changes(
    db: Session,
    draft: ProjectCatalogVersion | None,
    specs: tuple[_GroupSpec, ...],
) -> tuple[int, int]:
    if draft is None:
        return len(specs), sum(len(group.choices) for group in specs)
    groups_created = 0
    choices_created = 0
    for spec in specs:
        group, _ = _matching_group(db, draft.id, spec, [])
        if group is None:
            groups_created += 1
            choices_created += len(spec.choices)
            continue
        for choice_spec in spec.choices:
            choice, _ = _matching_choice(db, group.id, choice_spec, [])
            if choice is None:
                choices_created += 1
    return groups_created, choices_created


def migrate_store_catalog(db: Session, store_id: int, dry_run: bool = True) -> MigrationReport:
    """Create or complete reviewable draft catalogs for exactly one store."""

    if dry_run:
        with db.no_autoflush:
            return _migrate_store_catalog(db, store_id=store_id, dry_run=True)
    return _migrate_store_catalog(db, store_id=store_id, dry_run=False)


def _migrate_store_catalog(db: Session, store_id: int, dry_run: bool) -> MigrationReport:

    if db.get(Store, store_id) is None:
        raise ValueError(f"store {store_id} does not exist")

    report = MigrationReport()
    effective_at = datetime.now(UTC)
    addons_by_project = _collect_addons(db, store_id, report.warnings)
    projects = list(db.scalars(
        select(Project).where(Project.store_id == store_id).order_by(Project.id)
    ))
    for project in projects:
        specs = _group_specs(project, addons_by_project.get(project.id, ()), report.warnings)
        if not specs:
            continue
        draft = _latest_draft(db, project.id)
        if dry_run:
            groups_created, choices_created = _predict_group_changes(db, draft, specs)
            report.created_versions += int(draft is None)
            report.created_groups += groups_created
            report.created_choices += choices_created
            continue

        if draft is None:
            draft = ProjectCatalogVersion(
                project_id=project.id,
                version=_next_version(db, project.id),
                status="draft",
            )
            db.add(draft)
            db.flush()
            report.created_versions += 1
            if project.current_published_version_id is not None:
                published = db.get(ProjectCatalogVersion, project.current_published_version_id)
                if published is None or published.project_id != project.id or published.status != "published":
                    raise ValueError(f"project {project.code} has an invalid current published catalog pointer")
                copy_catalog_version_graph(db, published.id, draft.id)

        for group_order, spec in enumerate(specs):
            group, group_code = _matching_group(db, draft.id, spec, report.warnings)
            if group is None:
                group = ProjectOptionGroup(
                    catalog_version_id=draft.id,
                    code=group_code,
                    name=spec.name,
                    selection_mode="multiple",
                    required=False,
                    min_select=0,
                    max_select=len(spec.choices),
                    display_order=group_order,
                )
                db.add(group)
                db.flush()
                report.created_groups += 1

            for choice_order, choice_spec in enumerate(spec.choices):
                choice, choice_code = _matching_choice(db, group.id, choice_spec, report.warnings)
                if choice is None:
                    choice = ProjectOptionChoice(
                        option_group_id=group.id,
                        code=choice_code,
                        name=choice_spec.name,
                        choice_type=choice_spec.choice_type,
                        charge_mode=choice_spec.charge_mode,
                        display_order=choice_order,
                    )
                    db.add(choice)
                    db.flush()
                    report.created_choices += 1
                _reconcile_current_prices(db, choice, choice_spec, effective_at, report.warnings)

            group.max_select = int(db.scalar(select(func.count()).select_from(ProjectOptionChoice).where(
                ProjectOptionChoice.option_group_id == group.id
            )) or 0)

    return report


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store-id", type=int, required=True)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--dry-run", action="store_true", help="preview without writing (default)")
    modes.add_argument("--apply", action="store_true", help="write and commit the migration")
    args = parser.parse_args(argv)

    with SessionLocal() as db:
        report = migrate_store_catalog(db, store_id=args.store_id, dry_run=not args.apply)
        if args.apply:
            db.commit()
        print(json.dumps(asdict(report), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
