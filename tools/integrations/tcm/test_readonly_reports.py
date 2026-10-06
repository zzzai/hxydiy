import importlib.util
import json
from pathlib import Path
import sqlite3
import http.client
import os
import socket
import threading
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest


@pytest.fixture
def reports(tmp_path):
    source = Path(__file__).with_name("readonly_reports.py")
    spec = importlib.util.spec_from_file_location("tcm_readonly", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    path = tmp_path / "reports.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE tcm_reports(report_no TEXT PRIMARY KEY,phone TEXT,report_time TEXT,structured_data TEXT,heart_rate TEXT,blood_oxygen TEXT,moisture_index TEXT)")
        db.execute("CREATE INDEX ix_phone_time ON tcm_reports(phone,report_time)")
        for identifier, phone in (("R1", "13800138000"), ("R2", "13900139000"), ("PROBE-1", "13800138000")):
            payload = {"data": {"report_no": identifier, "phy_figure_infos": [{"phy_name": "平和质", "phy_point": 42}],
                       "face_image_url": "http://private.example/face", "report_print_url": "https://private.example/report"}}
            db.execute("INSERT INTO tcm_reports VALUES(?,?,?,?,?,?,?)", (identifier, phone, "2026-10-06 03:00:00", json.dumps(payload), "77.0", "92.0", "3 湿气一般"))
    app = FastAPI()
    app.include_router(module.build_router(path, "read-fixture", ("admin-fixture", "webhook-fixture")))
    with TestClient(app, client=("172.18.0.55", 40000)) as client:
        yield client, app, path


def test_read_credentials_minimal_list_owner_detail_and_probe_exclusion(reports):
    client, _, path = reports
    endpoint = "/api/tcm/readonly/reports"
    params = {}
    assert client.get(endpoint, params=params).status_code == 401
    for token in ("admin-fixture", "webhook-fixture"):
        assert client.get(endpoint, params=params, headers={"Authorization": "Bearer " + token}).status_code == 401
    headers = {"Authorization": "Bearer read-fixture", "X-TCM-Verified-Phone": "13800138000"}
    response = client.get(endpoint, params=params, headers=headers)
    assert response.status_code == 200
    assert response.json()["items"] == [{"report_id": "R1", "reported_at": "2026-10-06T03:00:00+00:00", "title": "检测报告"}]
    assert response.json()["has_more"] is False
    detail = client.get(endpoint + "/R1", params=params, headers=headers)
    assert detail.status_code == 200
    assert detail.json()["physiques"] == [{"name": "平和质", "score": 42.0}]
    assert detail.json()["heart_rate"] == 77.0
    assert "private.example" not in detail.text
    assert "13800138000" not in detail.text
    assert client.get(endpoint + "/R2", params=params, headers=headers).status_code == 404
    assert client.get(endpoint + "/PROBE-1", params=params, headers=headers).status_code == 404
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT count(*) FROM tcm_reports").fetchone()[0] == 3


def test_public_ip_spoofed_forward_header_and_invalid_query_rejected(reports):
    client, app, _ = reports
    endpoint = "/api/tcm/readonly/reports"
    headers = {"Authorization": "Bearer read-fixture", "X-TCM-Verified-Phone": "13800138000"}
    assert client.get(endpoint, headers={**headers, "X-TCM-Verified-Phone": "' OR 1=1 --"}).status_code == 422
    assert client.get(endpoint, params={"limit": 21}, headers=headers).status_code == 422
    assert client.get(endpoint, params={"phone": "13900139000"}, headers=headers).status_code == 422
    with TestClient(app, client=("8.8.8.8", 40000)) as public:
        assert public.get(endpoint, params={"phone": "13800138000"},
                          headers={**headers, "X-Forwarded-For": "172.18.0.55"}).status_code == 403


@pytest.mark.parametrize("token", ["", "admin-fixture", "webhook-fixture"])
def test_missing_or_reused_privileged_credential_disables_reader(reports, token):
    _, _, path = reports
    spec = importlib.util.spec_from_file_location("tcm_disabled", Path(__file__).with_name("readonly_reports.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    app = FastAPI()
    app.include_router(module.build_router(path, token, ("admin-fixture", "webhook-fixture")))
    with TestClient(app, client=("172.18.0.55", 40000)) as client:
        assert client.get("/api/tcm/readonly/reports", headers={"Authorization": "Bearer " + token,
                          "X-TCM-Verified-Phone": "13800138000"}).status_code == 503


def test_real_uvicorn_socket_loopback_source_preserves_network_and_credential_checks(reports):
    import uvicorn
    _, app, _ = reports
    bind = os.environ.get("TCM_SOCKET_TEST_BIND", "127.0.0.1")
    sock = socket.socket()
    sock.bind((bind, 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host=bind, port=port, proxy_headers=False,
                                          access_log=False, log_level="critical"))
    thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 5
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started, "Isolated socket server failed to start"
        for token, expected in (("wrong-fixture", 401), ("admin-fixture", 401),
                                ("webhook-fixture", 401), ("read-fixture", 200)):
            # Host-to-Docker-bridge traffic can be masqueraded outside the CIDR.
            # Bind the probe's existing allowed loopback source, not a spoofed header.
            connection = http.client.HTTPConnection(bind, port, timeout=3, source_address=("127.0.0.1", 0))
            try:
                connection.request("GET", "/api/tcm/readonly/reports", headers={
                    "Authorization": "Bearer " + token, "X-TCM-Verified-Phone": "13800138000",
                    "X-Forwarded-For": "8.8.8.8"})
                response = connection.getresponse()
                assert response.status == expected
                if expected == 200:
                    assert json.loads(response.read())["items"][0]["report_id"] == "R1"
                else:
                    response.read()
            finally:
                connection.close()
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        sock.close()
    assert not thread.is_alive()
