"""Public, crawler-readable project share pages for the customer H5."""

from html import escape
from json import dumps
from urllib.parse import quote, urlencode, urljoin, urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models import Project


router = APIRouter(tags=["share"])


def _public_url(path: str) -> str:
    base_url = settings.h5_public_base_url.rstrip("/") + "/"
    parsed = urlsplit(path)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return path
    if parsed.netloc:  # Do not turn a protocol-relative admin value into an external card image.
        return urljoin(base_url, "assets/hxy-mascot.webp")
    return urljoin(base_url, path.lstrip("/"))


def _share_urls(project: Project, store_id: int | None) -> tuple[str, str]:
    base_url = settings.h5_public_base_url.rstrip("/") + "/"
    project_path = f"share/project/{quote(project.code, safe='')}"
    query = urlencode({"store": store_id}) if store_id is not None else ""
    share_url = urljoin(base_url, project_path) + (f"?{query}" if query else "")
    detail_query = {"source": "project_share", "project": project.code}
    if store_id is not None:
        detail_query["store"] = store_id
    detail_url = base_url + "?" + urlencode(detail_query)
    return share_url, detail_url


@router.get("/share/project/{project_code}", response_class=HTMLResponse)
def project_share_page(
    project_code: str,
    store: int | None = Query(None, ge=1),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Render metadata for WeChat and other crawlers without exposing a customer session."""
    stmt = select(Project).where(
        Project.code == project_code,
        Project.publication_status == "published",
    )
    if store is not None:
        stmt = stmt.where(Project.store_id == store)
    project = db.scalar(stmt)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在或未发布")

    share_url, detail_url = _share_urls(project, store)
    title = f"荷小悦 · {project.name}"
    description = (project.summary or "荷小悦到店项目").strip()[:120]
    image_url = _public_url(project.image_url or "assets/hxy-mascot.webp")
    escaped_title = escape(title, quote=True)
    escaped_description = escape(description, quote=True)
    escaped_image = escape(image_url, quote=True)
    escaped_share_url = escape(share_url, quote=True)
    escaped_detail_url = escape(detail_url, quote=True)
    redirect_json = dumps(detail_url).replace("<", "\\u003c")
    body = f"""<!doctype html>
<html lang=\"zh-CN\">
  <head>
    <meta charset=\"UTF-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <meta name=\"description\" content=\"{escaped_description}\" />
    <link rel=\"canonical\" href=\"{escaped_share_url}\" />
    <meta property=\"og:type\" content=\"website\" />
    <meta property=\"og:title\" content=\"{escaped_title}\" />
    <meta property=\"og:description\" content=\"{escaped_description}\" />
    <meta property=\"og:image\" content=\"{escaped_image}\" />
    <meta property=\"og:image:alt\" content=\"{escaped_title}\" />
    <meta property=\"og:url\" content=\"{escaped_share_url}\" />
    <meta name=\"twitter:card\" content=\"summary_large_image\" />
    <meta name=\"twitter:title\" content=\"{escaped_title}\" />
    <meta name=\"twitter:description\" content=\"{escaped_description}\" />
    <meta name=\"twitter:image\" content=\"{escaped_image}\" />
    <title>{escaped_title}</title>
  </head>
  <body>
    <p>正在打开项目详情… <a href=\"{escaped_detail_url}\">点击继续</a></p>
    <script>window.location.replace({redirect_json});</script>
  </body>
</html>"""
    return HTMLResponse(body, headers={"Cache-Control": "no-store"})
