"""Employee-purpose adapter. No customer JWT or personal-report API delegation."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from fastapi import HTTPException


@dataclass(frozen=True)
class ServicePurposeEvidence:
    staff_id: int
    store_id: int
    customer_id: int
    occupancy_id: int
    purpose: str
    expires_at: datetime


@dataclass(frozen=True)
class TechnicianReportAccess:
    enabled: bool = False
    evidence_provider: Callable | None = None
    source: Callable | None = None


def get_technician_report_access():
    # Production remains disabled until an employee-specific source and evidence exist.
    return TechnicianReportAccess()


def unavailable():
    raise HTTPException(403, detail={"code": "REPORT_ACCESS_UNAVAILABLE", "message": "当前服务报告授权或来源不可用"})


def read_service_reports(access, *, staff_id, store_id, customer_id, occupancy_id):
    if not access.enabled or not access.evidence_provider or not access.source:
        unavailable()
    evidence = access.evidence_provider(staff_id=staff_id, store_id=store_id, customer_id=customer_id, occupancy_id=occupancy_id)
    if not isinstance(evidence, ServicePurposeEvidence):
        unavailable()
    expiry = evidence.expires_at
    if expiry.tzinfo is None:
        unavailable()
    if (evidence.staff_id, evidence.store_id, evidence.customer_id, evidence.occupancy_id, evidence.purpose) != (staff_id, store_id, customer_id, occupancy_id, "current_service") or expiry <= datetime.now(timezone.utc):
        unavailable()
    rows = access.source(store_id=store_id, customer_id=customer_id)
    if not isinstance(rows, list) or len(rows) > 1000:
        unavailable()
    result = []
    for row in rows:
        if not isinstance(row, dict) or row.get("store_id") != store_id or row.get("customer_id") != customer_id:
            unavailable()
        sections = row.get("sections")
        if not isinstance(sections, list) or len(sections) > 100:
            unavailable()
        clean = []
        for section in sections:
            if not isinstance(section, dict):
                unavailable()
            title, content = section.get("title"), section.get("content")
            if not isinstance(title, str) or not isinstance(content, str) or len(title) > 200 or len(content) > 10000 or any(url in (title + content).lower() for url in ("http:", "https:", "data:", "//")):
                unavailable()
            clean.append({"title": title, "content": content})
        report_id, title, created_at = row.get("id"), row.get("title"), row.get("created_at")
        if not isinstance(report_id, str) or not report_id or len(report_id) > 128 or not isinstance(title, str) or len(title) > 200 or any(url in (title + report_id).lower() for url in ("http:", "https:", "data:", "//")) or (created_at is not None and not isinstance(created_at, str)):
            unavailable()
        result.append({"id": report_id, "title": title, "created_at": created_at, "sections": clean})
    return result
