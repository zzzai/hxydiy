"""Read-only audit probes using an isolated in-memory database, never production."""

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "hxy-server"))
sys.path.insert(0, str(ROOT / "hxy-server" / "tests"))

from test_selection_closure_v2 import SelectionClosureV2Tests
from app.api.admin import create_staff_token
from app.api.selections import refresh_session_pricing
from app.core.config import settings
from app.models import MembershipCard, SelectionSession, User


def main():
    fixture = SelectionClosureV2Tests
    fixture.setUpClass()
    try:
        now = datetime.now(UTC)
        with fixture.SessionLocal() as db:
            user = User(openid="audit-source-member", is_member=False)
            db.add(user)
            db.flush()
            db.add(MembershipCard(
                user_id=user.id, store_id=fixture.store_id,
                source="audit", source_card_key="audit-only",
                card_type="stored", balance_cents=10000, status="active",
                started_at=now - timedelta(days=1),
            ))
            session = SelectionSession(
                id="audit-confirm", access_token_hash="audit-only",
                store_id=fixture.store_id, customer_id=user.id,
                status="submitted", items=[{"project_id": fixture.project_id}],
                diy_preferences={}, membership_verified_at=now,
            )
            db.add(session)
            db.flush()
            preview = refresh_session_pricing(db, session)
            db.commit()
        response = fixture.client.post(
            "/api/v1/admin/v2/selection-sessions/audit-confirm/confirm",
            headers={"Authorization": "Bearer " + create_staff_token(fixture.staff_id, "admin")},
        )
        with fixture.SessionLocal() as db:
            frozen = db.get(SelectionSession, "audit-confirm").pricing_snapshot
        print(json.dumps({
            "probe": "source_card_staff_confirmation",
            "http_status": response.status_code,
            "expected_member_cents": 2990,
            "preview_cents": preview.get("payable_total_cents"),
            "confirmed_cents": frozen.get("payable_total_cents"),
            "matches_expected": response.status_code == 200 and frozen.get("payable_total_cents") == 2990,
        }))
        with patch.object(settings, "environment", "production"), patch.object(settings, "wx_appsecret", ""):
            response = fixture.client.post("/api/v1/auth/login", json={"code": "audit-arbitrary-code"})
            print(json.dumps({
                "probe": "production_without_wx_secret",
                "http_status": response.status_code,
                "issued_token": bool(response.json().get("token")),
                "expected": "reject_unverified_login",
            }))
    finally:
        fixture.tearDownClass()


if __name__ == "__main__":
    main()
