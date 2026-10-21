"""Operation-level access capabilities shared by API and UI contracts.

The database role is only the outer shell. A store manager is also a
technician, but may only publish/unpublish store catalogue content rather than
edit headquarters master data. Keep that distinction explicit here so hidden
navigation is never treated as authorization.
"""

CAPABILITY_KEYS = (
    "self_service",
    "view_store_operations",
    "manage_store_resources",
    "manage_technicians",
    "toggle_catalog_publication",
    "manage_catalog_master",
    "follow_up_reviews",
    "view_analytics",
    "manage_customer_tags",
    "manage_marketing",
    "manage_automation",
    "manage_staff_accounts",
    "manage_headquarters",
)

_MANAGER = {
    "self_service": False,
    "view_store_operations": True,
    "manage_store_resources": True,
    "manage_technicians": True,
    "toggle_catalog_publication": True,
    "manage_catalog_master": False,
    "follow_up_reviews": True,
    "view_analytics": True,
    "manage_customer_tags": True,
    "manage_marketing": False,
    "manage_automation": False,
    "manage_staff_accounts": False,
    "manage_headquarters": False,
}

_TECHNICIAN = {key: key == "self_service" for key in CAPABILITY_KEYS}
_STAFF = {key: key == "view_store_operations" for key in CAPABILITY_KEYS}
_HEADQUARTERS = {key: True for key in CAPABILITY_KEYS}
_HEADQUARTERS["self_service"] = False


def staff_capabilities(role: str | None, store_id: int | None, technician_id: int | None) -> dict[str, bool]:
    """Return capabilities from the persisted account shape, fail closed."""
    if role == "admin" and store_id is None:
        return dict(_HEADQUARTERS)
    if role in {"admin", "manager"} and store_id is not None:
        return dict(_MANAGER)
    if role == "technician" and technician_id is not None and store_id is not None:
        return dict(_TECHNICIAN)
    if role == "staff" and store_id is not None:
        return dict(_STAFF)
    return {key: False for key in CAPABILITY_KEYS}
