from sqlalchemy.orm import Session

from app.models import Project, ProjectCatalogVersion, ProjectOptionGroup, Store


def make_catalog_version(
    db: Session,
    *,
    project_code: str,
    version: int = 1,
    status: str = "draft",
) -> ProjectCatalogVersion:
    store = Store(
        store_code=f"{project_code}-store",
        name="目录选项测试门店",
        address="测试地址",
    )
    db.add(store)
    db.flush()
    project = Project(
        store_id=store.id,
        code=project_code,
        category="catalog-option-test",
        name="目录选项测试项目",
    )
    db.add(project)
    db.flush()
    catalog_version = ProjectCatalogVersion(
        project_id=project.id,
        version=version,
        status=status,
    )
    db.add(catalog_version)
    db.flush()
    return catalog_version


def make_option_group(
    db: Session,
    catalog_version_id: int,
    *,
    code: str,
    name: str = "测试选项组",
) -> ProjectOptionGroup:
    group = ProjectOptionGroup(
        catalog_version_id=catalog_version_id,
        code=code,
        name=name,
    )
    db.add(group)
    db.flush()
    return group


def make_two_linked_projects(
    db: Session,
    *,
    prefix: str = "linked-project",
) -> tuple[Project, Project]:
    store = Store(
        store_code=f"{prefix}-store",
        name="关联项目测试门店",
        address="测试地址",
    )
    db.add(store)
    db.flush()
    projects = (
        Project(
            store_id=store.id,
            code=f"{prefix}-one",
            category="linked-project-test",
            name="关联项目一",
        ),
        Project(
            store_id=store.id,
            code=f"{prefix}-two",
            category="linked-project-test",
            name="关联项目二",
        ),
    )
    db.add_all(projects)
    db.flush()
    return projects
