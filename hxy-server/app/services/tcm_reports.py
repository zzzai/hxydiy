"""Bounded internal reader; never use webhook/admin credentials or redirects."""

import json
from urllib.parse import quote

import httpx
from fastapi import HTTPException
from pydantic import ValidationError

from app.core.config import settings
from app.schemas.tcm_reports import ReportDetail, ReportList


def source_client():
    return httpx.Client(timeout=httpx.Timeout(5, connect=2), follow_redirects=False, trust_env=False)


def read_report_source(phone, *, report_id=None, limit=20, offset=0):
    if not settings.tcm_reports_read_token or settings.tcm_reports_base_url != "http://172.18.0.1:18090":
        raise HTTPException(503, detail={"code": "TCM_UNAVAILABLE", "message": "报告服务暂不可用"})
    path = "/api/tcm/readonly/reports" + ("/" + quote(report_id, safe="") if report_id else "")
    params = {}
    if report_id is None:
        params.update(limit=limit, offset=offset)
    try:
        with source_client() as client:
            with client.stream("GET", settings.tcm_reports_base_url + path, params=params,
                               headers={"Authorization": "Bearer " + settings.tcm_reports_read_token,
                                        "X-TCM-Verified-Phone": phone}) as response:
                if response.status_code == 404 and report_id is not None:
                    raise HTTPException(404, "报告不存在")
                if response.status_code != 200:
                    raise HTTPException(503, detail={"code": "TCM_UNAVAILABLE", "message": "报告服务暂不可用"})
                parts, size = [], 0
                for part in response.iter_bytes():
                    size += len(part)
                    if size > 262144:
                        raise ValueError("bounded report response exceeded")
                    parts.append(part)
                result = json.loads(b"".join(parts))
        model = ReportDetail if report_id is not None else ReportList
        verified = model.model_validate(result)
        if report_id is not None and verified.report_id != report_id:
            raise ValueError("report identity mismatch")
        if report_id is None and (verified.limit != limit or verified.offset != offset or len(verified.items) > limit):
            raise ValueError("pagination mismatch")
        return verified.model_dump()
    except (httpx.HTTPError, ValueError, ValidationError):
        raise HTTPException(502, detail={"code": "TCM_SOURCE_INVALID", "message": "报告服务响应异常，请稍后再试"}) from None
