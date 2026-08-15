"""选单报价快照。DIY 仅提供门店结算参考，不创建支付订单。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Addon, PriceBook, Project


PROMO_FOOT_BATH_CODE = "hxy-qiqing-30"
FOOT_BATH_PROMOTION_CENTS = 2990
PRICE_TYPES = {"store", "group", "member"}


def price_type_for_member(is_member: bool) -> str:
    return "member" if is_member else "store"


def _prices(db: Session, project_id: int) -> dict[str, int]:
    rows = list(db.scalars(select(PriceBook).where(PriceBook.project_id == project_id)))
    by_type = {row.price_type: row.amount_cents for row in rows}
    store = by_type.get("store", by_type.get("group", by_type.get("member", 0)))
    return {
        "store": store,
        "group": by_type.get("group", store),
        # 与顾客端 priceOf 一致：member 缺价时回退 group，再回退 store。
        "member": by_type.get("member", by_type.get("group", store)),
    }


def _synthetic_project(db: Session, project_id: str) -> Project | None:
    """兼容历史选单字符串 ID；不再保留任何局部调理硬编码价格。"""
    if project_id == "local-strength":
        return db.scalar(select(Project).where(Project.code == "hxy-jubu-30"))
    return None


def calculate_selection_pricing(db: Session, items: list[dict], price_type: str = "store") -> dict:
    if price_type not in PRICE_TYPES:
        price_type = "store"
    lines: list[dict] = []
    store_subtotal = 0
    group_subtotal = 0
    member_subtotal = 0
    has_promo_foot_bath = False
    foot_bath_store_cents = 0
    foot_bath_group_cents = 0
    foot_bath_member_cents = 0
    local_parts: set[str] = set()

    for index, item in enumerate(items):
        if item.get("item_type") == "preference" or not item.get("chargeable", True):
            continue
        project_id = item.get("project_id")
        quantity = max(1, int(item.get("quantity") or 1))
        standalone_addon = db.get(Addon, item.get("addon_id")) if item.get("item_kind") == "standalone_addon" else None
        if standalone_addon:
            base_store = int(
                standalone_addon.store_price_cents
                if standalone_addon.store_price_cents is not None else standalone_addon.price_cents
            ) if standalone_addon.chargeable else 0
            base_group = base_store
            base_member = int(
                standalone_addon.member_price_cents
                if standalone_addon.member_price_enabled and standalone_addon.member_price_cents is not None
                else base_store
            )
            code = standalone_addon.code
            project = None
        else:
            project = db.get(Project, project_id) if isinstance(project_id, int) else None
            if project is None and isinstance(project_id, str):
                project = _synthetic_project(db, project_id)
            if project:
                prices = _prices(db, project.id)
                code = project.code
            else:
                prices, code = {"store": 0, "group": 0, "member": 0}, str(project_id)
            base_store = prices["store"]
            base_group = prices["group"]
            base_member = prices["member"]
        line_store = base_store * quantity
        line_group = base_group * quantity
        line_member = base_member * quantity
        addon_store = 0
        addon_member = 0
        for addon_id in item.get("addon_ids", []):
            addon = db.get(Addon, addon_id)
            if not addon or addon.publication_status != "published" or (addon.parent_project_id and addon.parent_project_id != project.id):
                continue
            if not addon.chargeable:
                continue
            addon_store += int(addon.store_price_cents if addon.store_price_cents is not None else addon.price_cents)
            addon_member += int(
                addon.member_price_cents
                if addon.member_price_enabled and addon.member_price_cents is not None
                else addon.store_price_cents if addon.store_price_cents is not None else addon.price_cents
            )
        line_store += addon_store * quantity
        line_member += addon_member * quantity
        line_group += addon_store * quantity
        store_subtotal += line_store
        group_subtotal += line_group
        member_subtotal += line_member
        preferences = [str(value).strip() for value in item.get("diy_preferences", []) if str(value).strip()]
        if code == PROMO_FOOT_BATH_CODE:
            has_promo_foot_bath = True
            # 减免只免泡脚项目本身的基础价，泡脚上另加的小项照常收费（与顾客端预览口径一致）。
            foot_bath_store_cents += base_store * quantity
            foot_bath_group_cents += base_group * quantity
            foot_bath_member_cents += base_member * quantity
        if code == "hxy-jubu-30" and preferences:
            local_parts.add(preferences[0])
        lines.append({
            "line_index": index,
            "project_id": project_id,
            "addon_id": item.get("addon_id"),
            "item_kind": item.get("item_kind", "project"),
            "name": item.get("name", project.name if project else standalone_addon.name if standalone_addon else "局部加强"),
            "quantity": quantity,
            "unit_store_price_cents": base_store + addon_store,
            "unit_group_price_cents": base_group + addon_store,
            "unit_member_price_cents": base_member + addon_member,
            "unit_payable_price_cents": (base_member + addon_member) if price_type == "member" else (base_group + addon_store) if price_type == "group" else (base_store + addon_store),
            "store_line_total_cents": line_store,
            "group_line_total_cents": line_group,
            "member_line_total_cents": line_member,
            "payable_line_total_cents": line_member if price_type == "member" else line_group if price_type == "group" else line_store,
            "addon_store_total_cents": addon_store * quantity,
            "addon_member_total_cents": addon_member * quantity,
        })

    qualified = has_promo_foot_bath and len(local_parts) >= 2
    # 两项局部调理：泡脚费按各价格带全额减免（门店价 3990 也全免）。
    adjustment_store = -foot_bath_store_cents if qualified else 0
    adjustment_group = -foot_bath_group_cents if qualified else 0
    adjustment_member = -foot_bath_member_cents if qualified else 0
    payable_adjustment = {
        "store": adjustment_store, "group": adjustment_group, "member": adjustment_member,
    }[price_type]
    return {
        "lines": lines,
        "store_subtotal_cents": store_subtotal,
        "group_subtotal_cents": group_subtotal,
        "member_subtotal_cents": member_subtotal,
        "promotion_code": "FOOT_BATH_TWO_LOCAL" if qualified else "",
        "promotion_name": "两项局部调理减免泡脚费" if qualified else "",
        "promotion_adjustment_cents": payable_adjustment,
        "store_total_cents": max(0, store_subtotal + adjustment_store),
        "group_total_cents": max(0, group_subtotal + adjustment_group),
        "member_total_cents": max(0, member_subtotal + adjustment_member),
        "applied_price_type": price_type,
        "payable_total_cents": max(0, {"store": store_subtotal, "group": group_subtotal, "member": member_subtotal}[price_type] + payable_adjustment),
        "distinct_local_parts": sorted(local_parts),
    }
