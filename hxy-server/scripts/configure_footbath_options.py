"""Prepare reviewable option-catalog drafts for footbath, massage and SPA projects."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import sys

SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.domain.catalog_options import copy_catalog_version_graph
from app.domain.membership_pricing import price_book_snapshot
from app.models import (
    OptionChoicePrice,
    PriceBook,
    Project,
    ProjectCatalogVersion,
    ProjectOptionChoice,
    ProjectOptionGroup,
)


FOOTBATH_CODES_IN_ORDER = ("hxy-qiqing-30", "hxy-xiangxiang-60", "hxy-xiaoqi-90")
FOOTBATH_CODES = frozenset(FOOTBATH_CODES_IN_ORDER)
SPA_CODES = frozenset(("hxy-spa-60", "hxy-spa-90"))
# 保持历史脚本常量兼容；新增 60 分钟 SPA 在门店确实存在时动态纳入。
TARGET_CODES = (*FOOTBATH_CODES_IN_ORDER, "hxy-tuina-70", "hxy-spa-90")
OPTIONAL_TARGET_CODES = ("hxy-spa-60",)
SMALL_OPTION_CODES = ("hxy-baguan-1", "hxy-guasha-1", "hxy-caier-30", "hxy-head-30")
LOCAL_BODY_PART_CHOICES = (
    ("local-shoulder-neck", "肩颈"),
    ("local-waist-hip", "腰臀"),
    ("local-leg", "腿部"),
    ("local-abdomen", "腹部"),
    ("local-foot", "足部"),
)
FOOTBATH_LIQUID_CHOICES = (
    ("liquid-ginger", "老姜", "暖足舒缓"),
    ("liquid-mugwort", "艾草", "草本泡浴"),
    ("liquid-rose", "玫瑰", "清香放松"),
    ("liquid-lavender", "薰衣草", "舒缓香气"),
    ("liquid-vinegar", "老醋", "清爽净足"),
)
PRESSURE_CHOICES = (
    ("pressure-light", "轻柔", "轻缓放松"),
    ("pressure-medium", "适中", "门店推荐"),
    ("pressure-strong", "强力", "力度更足"),
)
SPA_OIL_CHOICES = (
    ("spa-oil-lavender", "薰衣草精油", "舒缓花香"),
    ("spa-oil-rose", "玫瑰精油", "柔和花香"),
    ("spa-oil-sweet-orange", "甜橙精油", "清新果香"),
)


@dataclass
class FootbathOptionReport:
    projects: list[str] = field(default_factory=list)
    created_groups: int = 0
    created_choices: int = 0
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _GroupSpec:
    code: str
    name: str
    display_order: int
    projects: tuple[Project, ...] = ()
    preferences: tuple[tuple[str, str, str], ...] = ()
    selection_mode: str = "multiple"
    required: bool = False
    min_select: int = 0
    max_select: int | None = None


@dataclass(frozen=True)
class _ChoiceSpec:
    code: str
    name: str
    description: str
    linked_project: Project | None


def _choice_specs(spec: _GroupSpec) -> list[_ChoiceSpec]:
    """Return stable choice identity and label for a managed option group."""
    if spec.preferences:
        if spec.projects:
            raise ValueError(f"preference group cannot also link projects: {spec.code}")
        return [
            _ChoiceSpec(code=code, name=name, description=description, linked_project=None)
            for code, name, description in spec.preferences
        ]
    if spec.code == "local-strength":
        if len(spec.projects) != 1:
            raise ValueError("local-strength group requires exactly one linked project")
        project = spec.projects[0]
        return [
            _ChoiceSpec(code=code, name=name, description="", linked_project=project)
            for code, name in LOCAL_BODY_PART_CHOICES
        ]
    return [
        _ChoiceSpec(code=project.code, name=project.name, description="", linked_project=project)
        for project in spec.projects
    ]


def published_projects_by_code(
    db: Session,
    store_id: int,
    codes: tuple[str, ...],
) -> list[Project]:
    projects = list(
        db.scalars(
            select(Project)
            .where(
                Project.store_id == store_id,
                Project.code.in_(codes),
                Project.publication_status == "published",
            )
            .execution_options(populate_existing=True)
        )
    )
    by_code = {project.code: project for project in projects}
    missing = [code for code in codes if code not in by_code]
    if missing:
        raise ValueError(f"missing published target projects: {', '.join(missing)}")
    return [by_code[code] for code in codes]


def published_independent_projects_by_category(
    db: Session,
    store_id: int,
    category: str,
) -> list[Project]:
    candidates = list(
        db.scalars(
            select(Project)
            .where(
                Project.store_id == store_id,
                Project.category == category,
                Project.publication_status == "published",
            )
            .order_by(Project.display_order, Project.code, Project.id)
            .execution_options(populate_existing=True)
        )
    )
    projects: list[Project] = []
    for project in candidates:
        try:
            price_book_snapshot(db, project.id)
        except ValueError:
            continue
        projects.append(project)
    return projects


def published_independent_projects_by_codes(
    db: Session,
    store_id: int,
    codes: tuple[str, ...],
) -> list[Project]:
    candidates = list(
        db.scalars(
            select(Project)
            .where(
                Project.store_id == store_id,
                Project.code.in_(codes),
                Project.publication_status == "published",
            )
            .execution_options(populate_existing=True)
        )
    )
    by_code = {project.code: project for project in candidates}
    projects: list[Project] = []
    for code in codes:
        project = by_code.get(code)
        if project is None:
            continue
        try:
            price_book_snapshot(db, project.id)
        except ValueError:
            continue
        projects.append(project)
    found = {project.code for project in projects}
    missing = [code for code in codes if code not in found]
    if missing:
        raise ValueError(f"missing published or priced option projects: {', '.join(missing)}")
    return projects


def require_published_project_by_category(
    db: Session,
    store_id: int,
    category: str,
) -> Project:
    projects = published_independent_projects_by_category(db, store_id, category)
    if not projects:
        raise ValueError(f"no independently sellable published project in category: {category}")
    if len(projects) > 1:
        codes = ", ".join(project.code for project in projects)
        raise ValueError(f"multiple published projects in category {category}: {codes}")
    return projects[0]


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
    latest = db.scalar(
        select(func.max(ProjectCatalogVersion.version)).where(
            ProjectCatalogVersion.project_id == project_id
        )
    )
    return int(latest or 0) + 1


def _prediction_version(db: Session, project: Project) -> ProjectCatalogVersion | None:
    draft = _latest_draft(db, project.id)
    if draft is not None:
        return draft
    if project.current_published_version_id is None:
        return None
    published = db.get(ProjectCatalogVersion, project.current_published_version_id)
    if published is None or published.project_id != project.id or published.status != "published":
        raise ValueError(f"project {project.code} has an invalid current published catalog pointer")
    return published


def _existing_group(
    db: Session,
    version: ProjectCatalogVersion | None,
    code: str,
) -> ProjectOptionGroup | None:
    if version is None:
        return None
    return db.scalar(
        select(ProjectOptionGroup).where(
            ProjectOptionGroup.catalog_version_id == version.id,
            ProjectOptionGroup.code == code,
        )
    )


def _existing_choice(
    db: Session,
    group: ProjectOptionGroup | None,
    code: str,
) -> ProjectOptionChoice | None:
    if group is None:
        return None
    return db.scalar(
        select(ProjectOptionChoice).where(
            ProjectOptionChoice.option_group_id == group.id,
            ProjectOptionChoice.code == code,
        )
    )


def _specs_for_target(
    target: Project,
    small_projects: list[Project],
    local_project: Project,
) -> tuple[_GroupSpec, ...]:
    small_group = _GroupSpec(
        code="small-services",
        name="小项加购",
        display_order=30,
        projects=tuple(small_projects),
    )
    pressure_group = _GroupSpec(
        code="pressure",
        name="力度" if target.code in FOOTBATH_CODES else "手法力度",
        display_order=20 if target.code != "hxy-tuina-70" else 10,
        preferences=PRESSURE_CHOICES,
        selection_mode="single",
        required=True,
        min_select=1,
        max_select=1,
    )
    if target.code in FOOTBATH_CODES:
        return (
            _GroupSpec(
                code="footbath-liquid",
                name="泡脚液",
                display_order=10,
                preferences=FOOTBATH_LIQUID_CHOICES,
                selection_mode="single",
                required=True,
                min_select=1,
                max_select=1,
            ),
            pressure_group,
            small_group,
            _GroupSpec(
                code="local-strength",
                name="局部加强",
                display_order=40,
                projects=(local_project,),
            ),
        )
    if target.code == "hxy-tuina-70":
        return (
            pressure_group,
            _GroupSpec(
                code="small-services",
                name="小项加购",
                display_order=20,
                projects=tuple(small_projects),
            ),
        )
    if target.code in SPA_CODES:
        return (
            _GroupSpec(
                code="spa-oil",
                name="精油",
                display_order=10,
                preferences=SPA_OIL_CHOICES,
                selection_mode="single",
                required=True,
                min_select=1,
                max_select=1,
            ),
            pressure_group,
            small_group,
        )
    raise ValueError(f"unsupported target project: {target.code}")


def _predict_changes(
    db: Session,
    targets: list[Project],
    small_projects: list[Project],
    local_project: Project,
) -> tuple[int, int]:
    created_groups = 0
    created_choices = 0
    for target in targets:
        version = _prediction_version(db, target)
        for spec in _specs_for_target(target, small_projects, local_project):
            choice_specs = _choice_specs(spec)
            group = _existing_group(db, version, spec.code)
            if group is None:
                created_groups += 1
                created_choices += len(choice_specs)
                continue
            created_choices += sum(
                _existing_choice(db, group, choice.code) is None
                for choice in choice_specs
            )
    return created_groups, created_choices


def _ensure_draft(db: Session, target: Project) -> ProjectCatalogVersion:
    draft = _latest_draft(db, target.id)
    if draft is not None:
        return draft
    draft = ProjectCatalogVersion(
        project_id=target.id,
        version=_next_version(db, target.id),
        status="draft",
    )
    db.add(draft)
    db.flush()
    if target.current_published_version_id is not None:
        published = db.get(ProjectCatalogVersion, target.current_published_version_id)
        if published is None or published.project_id != target.id or published.status != "published":
            raise ValueError(f"project {target.code} has an invalid current published catalog pointer")
        copy_catalog_version_graph(db, published.id, draft.id)
    return draft


def _reconcile_group(
    db: Session,
    version: ProjectCatalogVersion,
    spec: _GroupSpec,
    report: FootbathOptionReport,
) -> None:
    choice_specs = _choice_specs(spec)
    qualifies_for_bundle = spec.code == "local-strength"
    group = _existing_group(db, version, spec.code)
    if group is None:
        group = ProjectOptionGroup(
            catalog_version_id=version.id,
            code=spec.code,
            name=spec.name,
            description="",
            selection_mode=spec.selection_mode,
            required=spec.required,
            min_select=spec.min_select,
            max_select=spec.max_select if spec.max_select is not None else len(choice_specs),
            display_order=spec.display_order,
        )
        db.add(group)
        db.flush()
        report.created_groups += 1
    else:
        group.name = spec.name
        group.description = ""
        group.selection_mode = spec.selection_mode
        group.required = spec.required
        group.min_select = spec.min_select
        group.max_select = spec.max_select if spec.max_select is not None else len(choice_specs)
        group.display_order = spec.display_order

    expected_codes = {choice.code for choice in choice_specs}
    existing_choices = list(
        db.scalars(
            select(ProjectOptionChoice).where(ProjectOptionChoice.option_group_id == group.id)
        )
    )
    for existing in existing_choices:
        if existing.code not in expected_codes:
            existing.status = "inactive"

    for display_order, choice_spec in enumerate(choice_specs):
        linked = choice_spec.linked_project
        choice = _existing_choice(db, group, choice_spec.code)
        choice_type = "linked_project" if linked is not None else "preference"
        charge_mode = "inherit_linked_price" if linked is not None else "free"
        if choice is None:
            choice = ProjectOptionChoice(
                option_group_id=group.id,
                code=choice_spec.code,
                name=choice_spec.name,
                description=choice_spec.description,
                choice_type=choice_type,
                linked_project_id=linked.id if linked is not None else None,
                pinned_linked_catalog_version_id=None,
                charge_mode=charge_mode,
                independently_visible=linked is not None,
                coupon_eligible=False,
                annual_gift_eligible=False,
                qualifies_for_foot_bath_bundle=qualifies_for_bundle and linked is not None,
                display_order=display_order,
                status="active",
            )
            db.add(choice)
            report.created_choices += 1
        else:
            has_local_prices = db.scalar(
                select(OptionChoicePrice.id)
                .where(OptionChoicePrice.option_choice_id == choice.id)
                .limit(1)
            ) is not None
            if has_local_prices:
                db.execute(
                    delete(OptionChoicePrice).where(OptionChoicePrice.option_choice_id == choice.id)
                )
            choice.name = choice_spec.name
            choice.description = choice_spec.description
            choice.choice_type = choice_type
            choice.linked_project_id = linked.id if linked is not None else None
            choice.pinned_linked_catalog_version_id = None
            choice.charge_mode = charge_mode
            choice.independently_visible = linked is not None
            choice.coupon_eligible = False
            choice.annual_gift_eligible = False
            choice.qualifies_for_foot_bath_bundle = qualifies_for_bundle and linked is not None
            choice.display_order = display_order
            choice.status = "active"
    db.flush()


def _lock_price_books(db: Session, project_ids: set[int]) -> None:
    if not project_ids:
        return
    list(
        db.scalars(
            select(PriceBook)
            .where(PriceBook.project_id.in_(sorted(project_ids)))
            .order_by(PriceBook.project_id, PriceBook.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )


def _locked_revalidated_configuration(
    db: Session,
    store_id: int,
) -> tuple[list[Project], list[Project], Project]:
    scope_ids = list(
        db.scalars(
            select(Project.id)
            .where(Project.store_id == store_id)
            .order_by(Project.id)
        )
    )
    scope_projects = list(
        db.scalars(
            select(Project)
            .where(Project.id.in_(scope_ids))
            .order_by(Project.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )
    if [project.id for project in scope_projects] != scope_ids:
        raise ValueError("a project disappeared while locking the configuration scope")
    _lock_price_books(db, set(scope_ids))

    target_codes = TARGET_CODES + tuple(
        code for code in OPTIONAL_TARGET_CODES
        if db.scalar(select(Project.id).where(
            Project.store_id == store_id,
            Project.code == code,
            Project.publication_status == "published",
        )) is not None
    )
    targets = published_projects_by_code(db, store_id, target_codes)
    small_projects = published_independent_projects_by_codes(db, store_id, SMALL_OPTION_CODES)
    if not small_projects:
        raise ValueError("no independently sellable published project in category: small")
    local_project = require_published_project_by_category(db, store_id, "local-strength")
    final_ids = {project.id for project in (*targets, *small_projects, local_project)}
    if not final_ids.issubset(set(scope_ids)):
        raise ValueError("a catalog project entered the configuration scope without a lock")
    return targets, small_projects, local_project


def reconcile_footbath_drafts(
    db: Session,
    targets: list[Project],
    small_projects: list[Project],
    local_project: Project,
    *,
    dry_run: bool = True,
) -> FootbathOptionReport:
    if not small_projects:
        raise ValueError("no independently sellable published project in category: small")
    report = FootbathOptionReport(projects=[project.code for project in targets])
    if dry_run:
        report.created_groups, report.created_choices = _predict_changes(
            db,
            targets,
            small_projects,
            local_project,
        )
        return report

    store_ids = {project.store_id for project in targets}
    if len(store_ids) != 1:
        raise ValueError("target projects must belong to exactly one store")
    targets, small_projects, local_project = _locked_revalidated_configuration(
        db,
        store_ids.pop(),
    )
    for target in targets:
        draft = _ensure_draft(db, target)
        for spec in _specs_for_target(target, small_projects, local_project):
            _reconcile_group(db, draft, spec, report)
    return report


def configure_footbath_option_drafts(
    db: Session,
    store_id: int,
    dry_run: bool = True,
) -> FootbathOptionReport:
    with db.no_autoflush:
        target_codes = TARGET_CODES + tuple(
            code for code in OPTIONAL_TARGET_CODES
            if db.scalar(select(Project.id).where(
                Project.store_id == store_id,
                Project.code == code,
                Project.publication_status == "published",
            )) is not None
        )
        targets = published_projects_by_code(db, store_id, target_codes)
        small_projects = published_independent_projects_by_codes(db, store_id, SMALL_OPTION_CODES)
        if not small_projects:
            raise ValueError("no independently sellable published project in category: small")
        local_project = require_published_project_by_category(db, store_id, "local-strength")
        return reconcile_footbath_drafts(
            db,
            targets,
            small_projects,
            local_project,
            dry_run=dry_run,
        )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store-id", type=int, required=True)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--dry-run", action="store_true", help="preview without writing (default)")
    modes.add_argument("--apply", action="store_true", help="write and commit draft catalogs")
    args = parser.parse_args(argv)

    with SessionLocal() as db:
        report = configure_footbath_option_drafts(
            db,
            store_id=args.store_id,
            dry_run=not args.apply,
        )
        if args.apply:
            db.commit()
        print(json.dumps(asdict(report), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
