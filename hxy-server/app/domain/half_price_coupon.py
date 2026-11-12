"""Read-only policy for manager-issued, scan-redeemed main-project vouchers."""

HALF_PRICE_SCOPE = "foot_spa_main"
HALF_PRICE_NAME = "足疗·SPA主项5折券"
HALF_PRICE_NOTE = "足疗、SPA主项按门店价5折；小项、加项、痛症调理及套盒不参与，不叠加会员价或其他优惠。到店由店长扫码核销。"


def is_half_price_coupon(template) -> bool:
    return bool(template and template.store_id is not None and template.code == f"half-price-50-s{template.store_id}")


def coupon_display_name(template) -> str:
    return HALF_PRICE_NAME if is_half_price_coupon(template) else template.name


def coupon_scope(template) -> dict:
    return {
        "store_id": template.store_id,
        "usage_scope": HALF_PRICE_SCOPE if is_half_price_coupon(template) else None,
        "scope_note": HALF_PRICE_NOTE if is_half_price_coupon(template) else "",
    }


def half_price_project_cents(project, prices: list[dict]) -> int | None:
    # Catalog categories are the business authority; never match display names.
    if project.publication_status != "published" or project.category not in {"bath", "care"}:
        return None
    store = next((row["amount_cents"] for row in prices if row["price_type"] == "store"), None)
    if store is None or store <= 0:
        return None
    # Keep currency in cents; an odd cent rounds the payable amount up.
    return store - store * 50 // 100
