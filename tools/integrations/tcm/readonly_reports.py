"""Standalone internal report reader; no ingestion imports or database writes."""

from contextlib import closing
from datetime import datetime, timezone
import ipaddress
import json
import math
from pathlib import Path
import re
import secrets
import sqlite3
from urllib.parse import quote

from fastapi import APIRouter, Depends, Header, HTTPException, Path as ApiPath, Query, Request


def reported_at(value):
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.replace(tzinfo=timezone.utc).isoformat() if parsed.tzinfo is None else parsed.isoformat()
    except (TypeError, ValueError):
        return None


def number(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def summary(row):
    return {"report_id": row["report_no"], "reported_at": reported_at(row["report_time"]), "title": "检测报告"}


def detail(row):
    try:
        data = json.loads(row["structured_data"] or "{}")
    except (TypeError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    if isinstance(data.get("data"), dict) and "report_no" not in data:
        data = data["data"]
    # Do not interpret conflicting source identities or return raw vendor payloads.
    if data.get("report_no") not in (None, row["report_no"]):
        data = {}
    physiques = []
    source = data.get("phy_figure_infos")
    for item in source[:9] if isinstance(source, list) else []:
        if isinstance(item, dict) and isinstance(item.get("phy_name"), str):
            physiques.append({"name": item["phy_name"][:64], "score": number(item.get("phy_point"))})
    moisture = re.match(r"^\s*(\d+)", str(row["moisture_index"] or ""))
    return {**summary(row), "physiques": physiques, "heart_rate": number(row["heart_rate"]),
            "blood_oxygen": number(row["blood_oxygen"]), "moisture": int(moisture[1]) if moisture else None}


def build_router(db_path, read_token, privileged_tokens):
    """Tokens are passed from private runtime configuration, never from the caller."""
    database = Path(db_path).resolve()
    uri = "file:" + quote(database.as_posix(), safe="/:") + "?mode=ro"
    network = ipaddress.ip_network("172.18.0.0/16")
    router = APIRouter(prefix="/api/tcm/readonly", tags=["internal-readonly-reports"])

    def authorize(request: Request, authorization: str | None = Header(default=None)):
        try:
            address = ipaddress.ip_address(request.client.host)
        except (ValueError, AttributeError):
            raise HTTPException(403, "Internal service access required") from None
        if address not in network and not address.is_loopback:
            raise HTTPException(403, "Internal service access required")
        if not read_token or any(token and secrets.compare_digest(read_token, token) for token in privileged_tokens):
            raise HTTPException(503, "Dedicated read credential not configured")
        supplied = authorization.removeprefix("Bearer ") if authorization and authorization.startswith("Bearer ") else ""
        if not secrets.compare_digest(supplied, read_token):
            raise HTTPException(401, "Read credential required")

    def query(sql, arguments):
        try:
            with closing(sqlite3.connect(uri, uri=True, timeout=2)) as db:
                db.row_factory = sqlite3.Row
                db.execute("PRAGMA query_only=ON")
                return db.execute(sql, arguments).fetchall()
        except sqlite3.Error:
            raise HTTPException(503, "Report source unavailable") from None

    def validate_query(request, allowed):
        if any(key not in allowed or len(request.query_params.getlist(key)) != 1 for key in request.query_params):
            raise HTTPException(422, "Identity override or unknown query rejected")

    @router.get("/reports", dependencies=[Depends(authorize)])
    def reports(request: Request, phone: str = Header(alias="X-TCM-Verified-Phone", pattern=r"^1[3-9]\d{9}$", min_length=11, max_length=11),
                limit: int = Query(20, ge=1, le=20), offset: int = Query(0, ge=0, le=100000)):
        validate_query(request, {"limit", "offset"})
        rows = query("SELECT report_no,report_time FROM tcm_reports WHERE phone=? AND report_no NOT LIKE 'PROBE-%' "
                     "ORDER BY report_time DESC,report_no DESC LIMIT ? OFFSET ?", (phone, limit + 1, offset))
        return {"items": [summary(row) for row in rows[:limit]], "limit": limit, "offset": offset, "has_more": len(rows) > limit}

    @router.get("/reports/{report_id}", dependencies=[Depends(authorize)])
    def report(request: Request, report_id: str = ApiPath(pattern=r"^[\w-]{1,128}$"),
               phone: str = Header(alias="X-TCM-Verified-Phone", pattern=r"^1[3-9]\d{9}$", min_length=11, max_length=11)):
        validate_query(request, set())
        rows = query("SELECT report_no,report_time,heart_rate,blood_oxygen,moisture_index,"
                     "CASE WHEN length(structured_data)<=524288 THEN structured_data ELSE NULL END AS structured_data "
                     "FROM tcm_reports WHERE phone=? AND report_no=? AND report_no NOT LIKE 'PROBE-%'", (phone, report_id))
        if not rows:
            raise HTTPException(404, "Report not found")
        return detail(rows[0])

    return router
