import os
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import select

from app.models import CustomerTag, CustomerTagRelation, CustomerSegment
from test_technician_customer_dossier import dossier


def setup_tags(factory, ids):
    with factory() as db:
        tags = [CustomerTag(store_id=ids["store_id"], name="Quiet preference"), CustomerTag(store_id=ids["store_id"], name="Archived", status="archived"), CustomerTag(store_id=ids["other_store_id"], name="Other store"), CustomerTag(store_id=ids["store_id"], name="Auto", tag_type="auto")]
        db.add_all(tags)
        db.flush()
        result = [t.id for t in tags]
        db.commit()
        return result


def test_atomic_idempotent_add_and_creator_versioned_revoke(dossier):
    client, factory, ids, headers, other_headers, _ = dossier
    tags = setup_tags(factory, ids)
    url = f"/api/v1/technician/occupancies/{ids['occupancies'][0]}/customer-tags"
    payload = {"tag_id": tags[0], "idempotency_key": "synthetic-key-0001"}
    first = client.post(url, headers=headers, json=payload)
    assert first.status_code == 200, first.text
    assert client.post(url, headers=headers, json=payload).json() == first.json()
    assert client.post(url, headers=headers, json={**payload, "tag_id": tags[1]}).status_code == 409
    duplicate = client.post(url, headers=headers, json={**payload, "idempotency_key": "synthetic-key-0002"})
    assert duplicate.status_code == 409
    view = client.get(url, headers=headers).json()
    assert [t["id"] for t in view["available_tags"]] == [tags[0]]
    assert view["items"][0]["sources"] == [{"kind": "contribution", "contribution_id": first.json()["id"], "owned_by_me": True, "version": 1}]
    other_url = f"/api/v1/technician/occupancies/{ids['occupancies'][1]}/customer-tags/contributions/{first.json()['id']}"
    assert client.request("DELETE", other_url, headers=other_headers, json={"expected_version": 1, "reason": "Synthetic correction"}).status_code == 404
    revoke_url = url + f"/contributions/{first.json()['id']}"
    assert client.request("DELETE", revoke_url, headers=headers, json={"expected_version": 2, "reason": "Synthetic correction"}).status_code == 409
    revoked = client.request("DELETE", revoke_url, headers=headers, json={"expected_version": 1, "reason": "Synthetic correction"})
    assert revoked.status_code == 200, revoked.text
    assert revoked.json() == {"id": first.json()["id"], "version": 2, "revoked": True}
    assert client.request("DELETE", revoke_url, headers=headers, json={"expected_version": 1, "reason": "Synthetic correction"}).json() == revoked.json()
    assert client.get(url, headers=headers).json()["items"] == []
    readded = client.post(url, headers=headers, json={**payload, "idempotency_key": "synthetic-key-0003"})
    assert readded.status_code == 200, readded.text
    assert readded.json()["id"] != first.json()["id"]


def test_invalid_dictionary_and_identity_override_are_rejected(dossier):
    client, factory, ids, headers, *_ = dossier
    tags = setup_tags(factory, ids)
    url = f"/api/v1/technician/occupancies/{ids['occupancies'][0]}/customer-tags"
    for tag in tags[1:]:
        assert client.post(url, headers=headers, json={"tag_id": tag, "idempotency_key": f"synthetic-{tag}"}).status_code == 404
    assert client.post(url, headers=headers, json={"tag_id": tags[0], "idempotency_key": "synthetic-override", "user_id": 999}).status_code == 422


def test_dictionary_delete_rejects_any_contribution_history_and_preserves_plain_delete(dossier):
    client, factory, ids, headers, _, manager_headers = dossier
    tags = setup_tags(factory, ids)
    plain = client.delete(f"/api/v1/admin/v2/tags/{tags[1]}", headers=manager_headers)
    assert plain.status_code == 200, plain.text
    url = f"/api/v1/technician/occupancies/{ids['occupancies'][0]}/customer-tags"
    created = client.post(url, headers=headers, json={"tag_id": tags[0], "idempotency_key": "delete-dictionary-guard"})
    assert created.status_code == 200, created.text
    for revoke_first in (False, True):
        if revoke_first:
            revoked = client.request("DELETE", url + f"/contributions/{created.json()['id']}", headers=headers, json={"expected_version": 1, "reason": "Synthetic correction"})
            assert revoked.status_code == 200, revoked.text
        result = client.delete(f"/api/v1/admin/v2/tags/{tags[0]}", headers=manager_headers)
        assert result.status_code == 409, result.text
        assert result.json()["detail"]["code"] == "TAG_HAS_CONTRIBUTIONS"
        with factory() as db:
            assert db.get(CustomerTag, tags[0]) is not None


def test_manager_legacy_remove_keeps_surviving_contribution_visible_and_counted_once(dossier):
    client, factory, ids, headers, other_headers, manager_headers = dossier
    tags = setup_tags(factory, ids)
    tag_id = tags[0]
    url = f"/api/v1/technician/occupancies/{ids['occupancies'][0]}/customer-tags"
    created = client.post(url, headers=headers, json={"tag_id": tag_id, "idempotency_key": "synthetic-union"})
    assert created.status_code == 200, created.text
    old = client.post(f"/api/v1/admin/v2/users/{ids['user_id']}/tags", headers=manager_headers, json={"tag_id": tag_id})
    assert old.status_code == 200, old.text
    assert len(client.get(url, headers=headers).json()["items"][0]["sources"]) == 2
    other_url = f"/api/v1/technician/occupancies/{ids['occupancies'][1]}/customer-tags"
    second_author = client.post(other_url, headers=other_headers, json={"tag_id": tag_id, "idempotency_key": "synthetic-author-two"})
    assert second_author.status_code == 200, second_author.text
    assert len(client.get(url, headers=headers).json()["items"][0]["sources"]) == 3
    with factory() as db:
        segment = CustomerSegment(store_id=ids["store_id"], name="Synthetic segment", conditions={"tags": ["Quiet preference"]})
        db.add(segment)
        db.commit()
        segment_id = segment.id
    for _ in range(2):
        listed = client.get(f"/api/v1/admin/v2/users?tag_id={tag_id}", headers=manager_headers)
        assert listed.status_code == 200, listed.text
        assert listed.json()["total"] == 1
        assert len(listed.json()["items"][0]["tags"]) == 1
        dictionary = client.get("/api/v1/admin/v2/tags", headers=manager_headers).json()
        assert next(t for t in dictionary if t["id"] == tag_id)["user_count"] == 1
        count = client.post(f"/api/v1/admin/v2/segments/{segment_id}/recount", headers=manager_headers)
        assert count.json()["user_count"] == 1
        deleted = client.delete(f"/api/v1/admin/v2/users/{ids['user_id']}/tags/{tag_id}", headers=manager_headers)
        assert deleted.status_code == 200, deleted.text
    assert client.get(url, headers=headers).json()["items"][0]["sources"][0]["kind"] == "contribution"
    assert len(client.get(url, headers=headers).json()["items"][0]["sources"]) == 2


@pytest.mark.skipif(not os.environ.get("WECOM_TEST_DATABASE_URL"), reason="Concurrent writes require isolated PostgreSQL")
def test_postgres_concurrent_add_keys_have_one_active_contribution(dossier):
    from app.models.customer_tag_contribution import CustomerTagContribution
    client, factory, ids, headers, *_ = dossier
    tag_id = setup_tags(factory, ids)[0]
    url = f"/api/v1/technician/occupancies/{ids['occupancies'][0]}/customer-tags"
    def submit(key):
        return client.post(url, headers=headers, json={"tag_id": tag_id, "idempotency_key": key})
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(submit, ["concurrent-key-one", "concurrent-key-two"]))
    assert sorted(r.status_code for r in results) == [200, 409], [r.text for r in results]
    with factory() as db:
        active = db.scalars(select(CustomerTagContribution).where(CustomerTagContribution.revoked_at.is_(None))).all()
        assert len(active) == 1


@pytest.mark.skipif(not os.environ.get("WECOM_TEST_DATABASE_URL"), reason="Concurrent writes require isolated PostgreSQL")
def test_postgres_concurrent_identical_key_replays_same_row(dossier):
    client, factory, ids, headers, *_ = dossier
    tag_id = setup_tags(factory, ids)[0]
    url = f"/api/v1/technician/occupancies/{ids['occupancies'][0]}/customer-tags"
    def submit(_):
        return client.post(url, headers=headers, json={"tag_id": tag_id, "idempotency_key": "concurrent-same-key"})
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(submit, range(2)))
    assert [r.status_code for r in results] == [200, 200], [r.text for r in results]
    assert results[0].json() == results[1].json()
