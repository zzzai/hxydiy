"""Loopback-only, synthetic HTTP harness; never part of the production application."""
import json
import os
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from sqlalchemy import select

from app.api.admin import create_staff_token, staff_snapshot
from app.api.staff_learning import content_hash, router
from app.core.config import settings
from app.db.session import Base, SessionLocal, engine
from app.models import Staff, Store, Technician
from app.models.staff_learning import LearningCourseVersion

if settings.environment != "test" or not settings.staff_learning_enabled or "learning-postgres-v8" not in settings.database_url or "/learning_test" not in settings.database_url:
    raise RuntimeError("Synthetic learning harness requires its dedicated test database")
Base.metadata.create_all(engine)
with SessionLocal() as db:
    if not db.get(Store, 1):
        db.add_all([Store(id=1, store_code="learning-demo-1", name="紫薇壹号店（隔离演示）", address="Synthetic", status="open"),
                    Store(id=2, store_code="learning-demo-2", name="其他门店（隔离演示）", address="Synthetic", status="open")])
        db.flush()
        db.add_all([Technician(id=9002, store_id=1, code="learning-a", name="技师 A（演示）", status="available"),
                    Technician(id=9003, store_id=1, code="learning-b", name="技师 B（演示）", status="available"),
                    Technician(id=9004, store_id=2, code="learning-other", name="异店技师（演示）", status="available")])
        db.flush()
        db.add_all([Staff(id=9001, username="learning-manager", role="manager", store_id=1, name="店长（演示）", password_hash="unused"),
                    Staff(id=9002, username="learning-a", role="technician", store_id=1, technician_id=9002, name="技师 A（演示）", password_hash="unused"),
                    Staff(id=9003, username="learning-b", role="technician", store_id=1, technician_id=9003, name="技师 B（演示）", password_hash="unused"),
                    Staff(id=9004, username="learning-other", role="technician", store_id=2, technician_id=9004, name="异店技师（演示）", password_hash="unused")])
        db.commit()
    for content in json.loads((Path(__file__).parent / "fixtures" / "learning-pilot-v8.json").read_text()):
        existing = db.scalar(select(LearningCourseVersion).where(LearningCourseVersion.code == content["id"], LearningCourseVersion.version == content["version"]))
        if existing:
            if existing.content_sha256 != content_hash(content):
                raise RuntimeError("Existing synthetic course must not be overwritten")
        else:
            db.add(LearningCourseVersion(id=str(uuid.uuid4()), code=content["id"], version=content["version"],
                status="pilot", content=content, content_sha256=content_hash(content), approval_reference=""))
    db.commit()

app = FastAPI()
app.include_router(router, prefix="/api/v1")


@app.middleware("http")
async def limit_preview_routes(request: Request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/__learning_preview__/session")
def session(actor: str):
    staff_id = {"manager": 9001, "tech-a": 9002, "tech-b": 9003, "other": 9004}.get(actor)
    if staff_id is None:
        raise HTTPException(404, "Unknown synthetic actor")
    with SessionLocal() as db:
        staff = db.get(Staff, staff_id)
        return {"token": create_staff_token(staff.id, staff.role), "staff": staff_snapshot(staff, "紫薇壹号店（隔离演示）")}


@app.get("/__learning_preview__/health")
def health():
    return {"ok": True, "synthetic": True}
