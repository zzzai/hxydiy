"""Customer-facing technician directory. Editorial profiles never grant booking rights."""

import json
import re
from functools import lru_cache
from pathlib import Path

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.service_portions import can_request
from app.models import Project, Staff, Store, Technician
from app.services.store_lifecycle import OPEN_STORE_STATUSES


class WorkPhoto(BaseModel):
    url: str
    caption: str


class ProfileCard(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str
    label: str
    technician_id: int | None = None
    experience: str = ""
    portrait_url: str = ""
    tags: list[str] = Field(default_factory=list)
    introduction: str = ""
    photos: list[WorkPhoto] = Field(default_factory=list)


class DirectoryProfile(ProfileCard):
    project_ids: list[int] = Field(default_factory=list)
    requestable_project_ids: list[int] = Field(default_factory=list)


class TechnicianDirectory(BaseModel):
    items: list[DirectoryProfile]


@lru_cache(maxsize=1)
def published_cards() -> dict[str, list[ProfileCard]]:
    path = Path(__file__).resolve().parents[2] / "content" / "public-technicians.json"
    stores = json.loads(path.read_text(encoding="utf-8"))
    result = {}
    for store_code, entries in stores.items():
        cards = [ProfileCard.model_validate(entry) for entry in entries]
        keys = [card.key for card in cards]
        bindings = [card.technician_id for card in cards if card.technician_id is not None]
        if len(set(keys)) != len(keys) or len(set(bindings)) != len(bindings):
            raise ValueError("Duplicate published technician profile")
        for card in cards:
            if not re.fullmatch(r"[a-z][a-z0-9-]{0,47}", card.key) or card.key.startswith("staff-"):
                raise ValueError("Invalid editorial technician key")
            for url in [card.portrait_url, *(photo.url for photo in card.photos)]:
                if url and not re.fullmatch(rf"/assets/technicians/{re.escape(store_code)}/[a-zA-Z0-9_-]+\.(?:jpe?g|png|webp|avif)", url):
                    raise ValueError("Use a published portrait or work photo belonging to this store")
        result[store_code] = cards
    return result


def store_directory(db: Session, store_id: int) -> TechnicianDirectory:
    store = db.get(Store, store_id)
    if store is None or store.status not in OPEN_STORE_STATUSES:
        raise HTTPException(404, "门店暂未开放")
    cards = [card for card in published_cards().get(store.store_code, [])
             if card.portrait_url or any(photo.url for photo in card.photos)]
    if not cards:
        return TechnicianDirectory(items=[])

    staff = db.scalars(select(Technician).join(Staff, Staff.technician_id == Technician.id).where(
        Technician.store_id == store.id, Staff.store_id == store.id,
        Staff.role == "technician", Staff.status == "active",
        Technician.status.in_(("available", "busy", "off")),
    ).order_by(Technician.sort_order, Technician.id)).all()
    roster = {person.id: person for person in staff if not re.search(
        r"模拟|演示|测试|验收|(?:^|[-_\s])(?:test|demo|smoke|fixture)(?:$|[-_\s\d])",
        f"{person.code} {person.name}", re.IGNORECASE,
    )}
    projects = db.scalars(select(Project.id).where(
        Project.store_id == store.id, Project.publication_status == "published",
        Project.independently_visible.is_(True),
    ).order_by(Project.display_order, Project.id)).all()
    items = []
    for card in cards:
        person = roster.get(card.technician_id)
        if card.technician_id is not None and person is None:
            continue
        skills = [pid for pid in projects if can_request(person, pid)] if person else []
        items.append(DirectoryProfile(**card.model_dump(), project_ids=skills,
                                      requestable_project_ids=skills if person and person.status in ("available", "busy") else []))
    return TechnicianDirectory(items=items)
