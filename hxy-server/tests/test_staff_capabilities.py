from app.domain.staff_capabilities import CAPABILITY_KEYS, staff_capabilities


def test_headquarters_admin_has_all_capabilities_but_not_self_service():
    capabilities = staff_capabilities("admin", None, None)
    assert all(capabilities[key] for key in CAPABILITY_KEYS if key != "self_service")
    assert capabilities["self_service"] is False


def test_manager_has_store_operations_but_not_master_data_or_accounts():
    capabilities = staff_capabilities("manager", 1, 2)
    assert capabilities["view_store_operations"] is True
    assert capabilities["toggle_catalog_publication"] is True
    assert capabilities["follow_up_reviews"] is True
    assert capabilities["manage_catalog_master"] is False
    assert capabilities["manage_staff_accounts"] is False
    assert capabilities["manage_headquarters"] is False


def test_technician_and_staff_are_fail_closed():
    technician = staff_capabilities("technician", 1, 2)
    assert technician["self_service"] is True
    assert technician["view_store_operations"] is False
    staff = staff_capabilities("staff", 1, None)
    assert staff["view_store_operations"] is True
    assert staff["manage_catalog_master"] is False
    assert staff_capabilities("unknown", 1, None) == {key: False for key in CAPABILITY_KEYS}
