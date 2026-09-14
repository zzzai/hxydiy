"""Prepare narrow, versioned five-formula drafts for the footbath projects."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select
from app.db.session import SessionLocal
from app.domain.catalog_options import copy_catalog_version_graph, lock_catalog_projects, validate_catalog_version
from app.models import Project, ProjectCatalogVersion, ProjectOptionChoice, ProjectOptionGroup

FORMULAS = (
    ('formula-wood', '舒心解压', '最近有点忙，想松一松\n玫瑰花 · 佛手 · 合欢皮'),
    ('formula-fire', '筋骨轻松', '久坐久站，想舒展一下\n桂枝 · 丹参 · 鸡血藤'),
    ('formula-earth', '轻盈畅快', '身体沉沉的，想轻松一点\n茯苓 · 薏苡仁 · 陈皮'),
    ('formula-metal', '清润放松', '想清清爽爽地放松一下\n桑叶 · 菊花 · 百合'),
    ('formula-water', '温暖养护', '手脚容易凉，想暖一暖\n杜仲 · 桑寄生 · 淫羊藿'),
)
FOOTBATH_CODES = ('hxy-qiqing-30', 'hxy-xiangxiang-60', 'hxy-xiaoqi-90')


def prepare_herbal_formulas(
    db,
    store_id: int,
    *,
    project_code: str = 'hxy-qiqing-30',
    apply: bool = False,
) -> dict:
    project = db.scalar(select(Project).where(Project.store_id == store_id, Project.code == project_code))
    if project is None:
        raise ValueError(f'footbath project not found: {project_code}')
    if apply:
        project = lock_catalog_projects(db, [project.id])[project.id]
    published = db.get(ProjectCatalogVersion, project.current_published_version_id)
    if published is None or published.project_id != project.id or published.status != 'published':
        raise ValueError('valid published catalog required')
    existing_draft = db.scalar(select(ProjectCatalogVersion.id).where(
        ProjectCatalogVersion.project_id == project.id, ProjectCatalogVersion.status == 'draft'))
    if existing_draft is not None:
        raise ValueError('existing draft requires review; refusing to overwrite')
    group = db.scalar(select(ProjectOptionGroup).where(
        ProjectOptionGroup.catalog_version_id == published.id,
        ProjectOptionGroup.code.in_(['footbath-liquid', 'footbath-formula'])))
    if group is None:
        raise ValueError('published herbal preference group missing')
    choices = list(db.scalars(select(ProjectOptionChoice).where(ProjectOptionChoice.option_group_id == group.id)))
    if any(c.choice_type != 'preference' or c.charge_mode != 'free' for c in choices):
        raise ValueError('only a free preference group may be replaced')
    formula_codes = {code for code, _, _ in FORMULAS}
    refresh_existing_formulas = group.code == 'footbath-formula'
    if refresh_existing_formulas and {choice.code for choice in choices if choice.status == 'active'} != formula_codes:
        raise ValueError('published formula codes do not match the approved five-formula set')
    report = {'status': 'preview', 'project_id': project.id, 'project_code': project.code, 'source_version_id': published.id,
              'formulas': [name for _, name, _ in FORMULAS],
              'operation': 'refresh_existing_formulas' if refresh_existing_formulas else 'replace_legacy_preferences'}
    if not apply:
        return report
    next_version = int(db.scalar(select(func.max(ProjectCatalogVersion.version)).where(
        ProjectCatalogVersion.project_id == project.id)) or 0) + 1
    draft = ProjectCatalogVersion(project_id=project.id, version=next_version, status='draft')
    db.add(draft)
    db.flush()
    copy_catalog_version_graph(db, published.id, draft.id)
    copied = db.scalar(select(ProjectOptionGroup).where(
        ProjectOptionGroup.catalog_version_id == draft.id,
        ProjectOptionGroup.code == ('footbath-formula' if refresh_existing_formulas else 'footbath-liquid')))
    if copied is None:
        raise ValueError('copied herbal preference group missing')
    copied.code = 'footbath-formula'
    copied.name = '草本方'
    copied.description = '五行草本 · 选一方更适合今天的状态'
    copied_choices = list(db.scalars(select(ProjectOptionChoice).where(ProjectOptionChoice.option_group_id == copied.id)))
    if refresh_existing_formulas:
        by_code = {choice.code: choice for choice in copied_choices}
        for order, (code, name, description) in enumerate(FORMULAS):
            choice = by_code[code]
            choice.name, choice.description = name, description
            choice.display_order, choice.status = order, 'active'
    else:
        for choice in copied_choices:
            choice.status = 'inactive'
        for order, (code, name, description) in enumerate(FORMULAS):
            db.add(ProjectOptionChoice(option_group_id=copied.id, code=code, name=name,
                description=description, choice_type='preference', charge_mode='free',
                independently_visible=False, display_order=order, status='active'))
    db.flush()
    errors = validate_catalog_version(db, draft.id)
    if errors:
        raise ValueError(f'catalog validation failed: {errors}')
    return {**report, 'status': 'draft_prepared', 'draft_version_id': draft.id}


def prepare_footbath_herbal_formulas(db, store_id: int, *, apply: bool = False) -> dict:
    """Create one reviewable five-formula draft per published footbath project."""
    if apply:
        with db.begin_nested():
            projects = [
                prepare_herbal_formulas(db, store_id, project_code=code, apply=True)
                for code in FOOTBATH_CODES
            ]
    else:
        projects = [
            prepare_herbal_formulas(db, store_id, project_code=code, apply=False)
            for code in FOOTBATH_CODES
        ]
    return {
        'status': 'draft_prepared' if apply else 'preview',
        'projects': projects,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--store-id', required=True, type=int)
    parser.add_argument('--apply', action='store_true', help='prepare draft only; never auto-publish')
    args = parser.parse_args()
    with SessionLocal() as db:
        result = prepare_footbath_herbal_formulas(db, args.store_id, apply=args.apply)
        if args.apply:
            db.commit()
        print(json.dumps(result, ensure_ascii=False))
