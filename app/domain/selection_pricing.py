"""选单报价快照。DIY 仅提供门店结算参考，不创建支付订单。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Addon, Project
from app.domain.membership_pricing import price_book_prices


PROMO_FOOT_BATH_CODE = "hxy-qiqing-30"
FOOT_BATH_PROMOTION_CENTS = 2990
PRICE_TYPES = {"store", "group", "member"}


def price_type_for_member(is_member: bool) -> str:
    return "member" if is_member else "store"


def _prices(db: Session, project_id: int) -> dict[str, int]:
    try:
        return price_book_prices(db, project_id)
    except ValueError:
        # 历史选单预览允许资料未补齐的项目以 0 元继续保存；严格缺价错误留给确认价/选项收费接口。
        return {"store": 0, "group": 0, "member": 0}


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
    foot_bath_store_units: list[int] = []
    foot_bath_group_units: list[int] = []
    foot_bath_member_units: list[int] = []
    qualified_local_units = 0
    local_parts: set[str] = set()
    legacy_local_parts: set[str] = set()

    for index, item in enumerate(items):
        if _first_value(item, "item_type") == "preference" or not _is_chargeable(item):
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
        preferences = _preferences(item)
        item_code = _first_value(item, "code") or code
        if item_code == PROMO_FOOT_BATH_CODE:
            # 减免只免泡脚项目本身的基础价，泡脚上另加的小项照常收费（与顾客端预览口径一致）。
            confirmed_base = _confirmed_base_price(item)
            foot_bath_store_units.extend([confirmed_base if confirmed_base is not None else base_store] * quantity)
            foot_bath_group_units.extend([confirmed_base if confirmed_base is not None else base_group] * quantity)
            foot_bath_member_units.extend([confirmed_base if confirmed_base is not None else base_member] * quantity)
        if _counts_for_foot_bath_bundle(item, code):
            if _explicit_bundle_qualification(item):
                qualified_local_units += quantity
            elif item_code == "hxy-jubu-30" and preferences:
                legacy_local_parts.add(preferences[0])
            if preferences:
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

    qualified_local_units += len(legacy_local_parts)
    matched_foot_baths = min(len(foot_bath_store_units), qualified_local_units // 2)
    qualified = matched_foot_baths > 0
    # 两项合格局部调理匹配一个泡脚单位；只免泡脚项目本身的基础价，不免 addon/升级。
    adjustment_store = -sum(foot_bath_store_units[:matched_foot_baths])
    adjustment_group = -sum(foot_bath_group_units[:matched_foot_baths])
    adjustment_member = -sum(foot_bath_member_units[:matched_foot_baths])
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
        "qualified_local_unit_count": qualified_local_units,
        "matched_foot_bath_count": matched_foot_baths,
    }


def _snapshot(item: dict) -> dict:
    snapshot = item.get("snapshot")
    return snapshot if isinstance(snapshot, dict) else {}


def _as_dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def _resolved_charge(item: dict) -> dict:
    return _as_dict(item.get("resolved_charge")) or _as_dict(_snapshot(item).get("resolved_charge"))


def _choice_snapshot(item: dict) -> dict:
    resolved = _resolved_charge(item)
    return (
        _as_dict(item.get("choice_snapshot"))
        or _as_dict(_snapshot(item).get("choice_snapshot"))
        or _as_dict(resolved.get("choice_snapshot"))
    )


def _known_sources(item: dict) -> list[dict]:
    snapshot = _snapshot(item)
    resolved = _resolved_charge(item)
    choice_snapshot = _choice_snapshot(item)
    return [item, snapshot, resolved, choice_snapshot]


def _first_value(item: dict, key: str):
    for source in _known_sources(item):
        if key in source:
            return source.get(key)
    return None


def _is_chargeable(item: dict) -> bool:
    chargeable = _first_value(item, "chargeable")
    return True if chargeable is None else bool(chargeable)


def _preferences(item: dict) -> list[str]:
    values = _first_value(item, "diy_preferences") or _first_value(item, "preferences")
    if isinstance(values, list):
        return [str(value).strip() for value in values if str(value).strip()]
    part = _first_value(item, "body_part") or _first_value(item, "part")
    return [str(part).strip()] if part and str(part).strip() else []


def _confirmed_base_price(item: dict) -> int | None:
    value = _first_value(item, "confirmed_base_price_cents")
    return int(value) if value is not None else None


def _explicit_bundle_qualification(item: dict) -> bool | None:
    value = _first_value(item, "qualifies_for_foot_bath_bundle")
    if value is not None:
        return bool(value)
    return None


def _counts_for_foot_bath_bundle(item: dict, resolved_code: str | None = None) -> bool:
    state = _first_value(item, "state")
    if state is not None and state not in {"pending", "confirmed", "in_service", "completed"}:
        return False
    if _first_value(item, "item_type") == "preference":
        return False
    if not _is_chargeable(item):
        return False
    if (
        _first_value(item, "price_basis") == "annual_gift"
        or _first_value(item, "basis") == "annual_gift"
        or bool(_first_value(item, "annual_gift_applied"))
    ):
        return False
    explicit = _explicit_bundle_qualification(item)
    if explicit is not None:
        return explicit
    code = _first_value(item, "code") or resolved_code
    preferences = _preferences(item)
    return code == "hxy-jubu-30" and bool(preferences)
