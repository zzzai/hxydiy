"""Prepare reviewable option-catalog drafts for the three footbath projects."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import sys

SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.domain.catalog_options import copy_catalog_version_graph, lock_catalog_projects
from app.domain.membership_pricing import price_book_snapshot
from app.models import Project, ProjectCatalogVersion, ProjectOptionChoice, ProjectOptionGroup


TARGET_CODES = ("hxy-qiqing-30", "hxy-xiangxiang-60", "hxy-xiaoqi-90")


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
    projects: tuple[Project, ...]
    display_order: int


def published_projects_by_code(
    db: Session,
    store_id: int,
    codes: tuple[str, ...],
) -> list[Project]:
    projects = list(
        db.scalars(
            select(Project).where(
                Project.store_id == store_id,
                Project.code.in_(codes),
                Project.publication_status == "published",
            )
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


def _predict_changes(
    db: Session,
    targets: list[Project],
    specs: tuple[_GroupSpec, ...],
) -> tuple[int, int]:
    created_groups = 0
    created_choices = 0
    for target in targets:
        version = _prediction_version(db, target)
        for spec in specs:
            group = _existing_group(db, version, spec.code)
            if group is None:
                created_groups += 1
                created_choices += len(spec.projects)
                continue
            created_choices += sum(
                _existing_choice(db, group, project.code) is None
                for project in spec.projects
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
    group = _existing_group(db, version, spec.code)
    if group is None:
        group = ProjectOptionGroup(
            catalog_version_id=version.id,
            code=spec.code,
            name=spec.name,
            selection_mode="multiple",
            required=False,
            min_select=0,
            max_select=len(spec.projects),
            display_order=spec.display_order,
        )
        db.add(group)
        db.flush()
        report.created_groups += 1
    else:
        group.name = spec.name
        group.selection_mode = "multiple"
        group.required = False
        group.min_select = 0
        group.max_select = len(spec.projects)
        group.display_order = spec.display_order

    for display_order, linked in enumerate(spec.projects):
        choice = _existing_choice(db, group, linked.code)
        if choice is None:
            choice = ProjectOptionChoice(
                option_group_id=group.id,
                code=linked.code,
                name=linked.name,
                choice_type="linked_project",
                linked_project_id=linked.id,
                charge_mode="inherit_linked_price",
                independently_visible=True,
                display_order=display_order,
                status="active",
            )
            db.add(choice)
            report.created_choices += 1
        else:
            choice.name = linked.name
            choice.choice_type = "linked_project"
            choice.linked_project_id = linked.id
            choice.pinned_linked_catalog_version_id = None
            choice.charge_mode = "inherit_linked_price"
            choice.independently_visible = True
            choice.display_order = display_order
            choice.status = "active"
    db.flush()


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
    specs = (
        _GroupSpec("small-services", "小项", tuple(small_projects), 10),
        _GroupSpec("local-strength", "局部加强", (local_project,), 20),
    )
    report = FootbathOptionReport(projects=[project.code for project in targets])
    if dry_run:
        report.created_groups, report.created_choices = _predict_changes(db, targets, specs)
        return report

    locked = lock_catalog_projects(
        db,
        [project.id for project in (*targets, *small_projects, local_project)],
    )
    if len(locked) != len({project.id for project in (*targets, *small_projects, local_project)}):
        raise ValueError("a catalog project disappeared while acquiring locks")
    for target in targets:
        draft = _ensure_draft(db, locked[target.id])
        for spec in specs:
            locked_spec = _GroupSpec(
                spec.code,
                spec.name,
                tuple(locked[project.id] for project in spec.projects),
                spec.display_order,
            )
            _reconcile_group(db, draft, locked_spec, report)
    return report


def configure_footbath_option_drafts(
    db: Session,
    store_id: int,
    dry_run: bool = True,
) -> FootbathOptionReport:
    with db.no_autoflush:
        targets = published_projects_by_code(db, store_id, TARGET_CODES)
        small_projects = published_independent_projects_by_category(db, store_id, "small")
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

    if args.apply:
        environment = settings.environment.strip().lower()
        if environment not in {"local", "test"}:
            scheme = settings.database_url.split(":", 1)[0] or "unknown"
            parser.error(
                f"--apply is refused: environment={environment or 'unknown'} "
                f"target={scheme}://<redacted>"
            )

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
