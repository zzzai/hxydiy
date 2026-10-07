import httpx
import pytest
from fastapi import HTTPException

from app.services import tcm_reports as source


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(source.settings, "tcm_reports_read_token", "isolated-read-fixture")
    monkeypatch.setattr(source.settings, "tcm_reports_base_url", "http://172.18.0.1:18090")


def transport(monkeypatch, handler):
    monkeypatch.setattr(source, "source_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))


def test_verified_phone_never_in_url_and_whitelist_drops_vendor_links(enabled, monkeypatch):
    def handler(request):
        assert "phone" not in str(request.url)
        assert request.headers["X-TCM-Verified-Phone"] == "13800138000"
        return httpx.Response(200, json={"report_id": "R1", "title": "检测报告", "face_url": "https://private.invalid/face"})
    transport(monkeypatch, handler)
    result = source.read_report_source("13800138000", report_id="R1")
    assert result["report_id"] == "R1"
    assert "face_url" not in result
    assert result["original_report_url"] is None


def test_original_link_validated_again_by_diy_and_missing_keeps_summary(enabled, monkeypatch):
    link="https://yk.qianmaitcm.com/print_smart_healthcare/#/discriminateRingReport?reportId=R1"
    for supplied, expected in [(link,link),(link.replace('reportId=R1','reportId=R2'),None),(link.replace('yk.qianmaitcm.com','evil.invalid'),None),(None,None)]:
        transport(monkeypatch,lambda request:httpx.Response(200,json={"report_id":"R1","original_report_url":supplied}))
        assert source.read_report_source("13800138000",report_id="R1")["original_report_url"] == expected


@pytest.mark.parametrize("status", [301, 302, 401, 403, 500, 503])
def test_upstream_failure_is_generic_and_redirects_not_followed(enabled, monkeypatch, status):
    transport(monkeypatch, lambda request: httpx.Response(status, headers={"Location": "http://169.254.169.254/latest"},
                                                         text="private upstream body"))
    with pytest.raises(HTTPException) as error:
        source.read_report_source("13800138000")
    assert error.value.status_code == 503
    assert "private" not in str(error.value.detail)


def test_identity_mismatch_oversize_timeout_and_unconfigured_fail_closed(enabled, monkeypatch):
    transport(monkeypatch, lambda request: httpx.Response(200, json={"report_id": "R2"}))
    with pytest.raises(HTTPException) as mismatch:
        source.read_report_source("13800138000", report_id="R1")
    assert mismatch.value.status_code == 502
    transport(monkeypatch, lambda request: httpx.Response(200, content=b"x" * 262145))
    with pytest.raises(HTTPException) as oversized:
        source.read_report_source("13800138000")
    assert oversized.value.status_code == 502
    def timeout(request):
        raise httpx.ReadTimeout("do not expose upstream URL", request=request)
    transport(monkeypatch, timeout)
    with pytest.raises(HTTPException) as timed_out:
        source.read_report_source("13800138000")
    assert timed_out.value.status_code == 502
    monkeypatch.setattr(source.settings, "tcm_reports_base_url", "http://169.254.169.254")
    with pytest.raises(HTTPException) as disabled:
        source.read_report_source("13800138000")
    assert disabled.value.status_code == 503


@pytest.mark.parametrize("payload", [{"report_id": "R1", "heart_rate": float("nan")},
                                      {"report_id": "R1", "physiques": [{"name": "fixture", "score": float("inf")}] }])
def test_nonfinite_values_rejected(enabled, monkeypatch, payload):
    import json
    transport(monkeypatch, lambda request: httpx.Response(200, content=json.dumps(payload)))
    with pytest.raises(HTTPException) as error:
        source.read_report_source("13800138000", report_id="R1")
    assert error.value.status_code == 502


def test_missing_credential_does_not_contact_source(enabled, monkeypatch):
    monkeypatch.setattr(source.settings, "tcm_reports_read_token", "")
    def forbidden(request):
        pytest.fail("Disabled reader must not contact upstream")
    transport(monkeypatch, forbidden)
    with pytest.raises(HTTPException) as error:
        source.read_report_source("13800138000")
    assert error.value.status_code == 503
