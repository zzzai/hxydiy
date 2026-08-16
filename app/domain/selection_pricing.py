"""选单报价快照。DIY 仅提供门店结算参考，不创建支付订单。"""

from datetime import UTC, datetime
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Addon, Project
from app.domain.membership_pricing import PriceContext, confirmed_price_for_line, price_book_prices


PROMO_FOOT_BATH_CODE = "hxy-qiqing-30"
PRICE_TYPES = {"store", "group", "member"}
BUNDLE_CONFIRMED_STATES = {"confirmed"}


def price_type_for_member(
    is_member: bool,
    member_expire_at: datetime | None = None,
    confirmed_at: datetime | None = None,
    member_type: str | None = None,
) -> str:
    if is_member and member_type == "annual" and member_expire_at is None:
        return "store"
    if is_member and member_expire_at is not None:
        current = confirmed_at or datetime.now(UTC)
        expires = member_expire_at.replace(tzinfo=UTC) if member_expire_at.tzinfo is None else member_expire_at.astimezone(UTC)
        current = current.replace(tzinfo=UTC) if current.tzinfo is None else current.astimezone(UTC)
        if expires <= current:
            return "store"
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


def calculate_selection_pricing(
    db: Session,
    items: list[dict],
    price_type: str = "store",
    price_context: PriceContext | None = None,
) -> dict:
    if price_type not in PRICE_TYPES:
        price_type = "store"
    lines: list[dict] = []
    store_subtotal = 0
    group_subtotal = 0
    member_subtotal = 0
    confirmation_payable_subtotal = 0
    foot_bath_units: list[tuple[int, int, int, int | None]] = []
    local_bundle_units: list[tuple[str, str | None]] = []
    seen_bundle_service_lines: set[tuple[str, str | int]] = set()
    local_parts: set[str] = set()

    for index, item in enumerate(items):
        if _first_value(item, "item_type") == "preference" or not _is_chargeable(item):
            continue
        project_id = item.get("project_id")
        quantity = max(1, int(item.get("quantity") or 1))
        is_standalone_addon = item.get("item_kind") == "standalone_addon"
        standalone_addon = db.get(Addon, item.get("addon_id")) if is_standalone_addon else None
        if price_context is not None and is_standalone_addon and (
            standalone_addon is None
            or standalone_addon.publication_status != "published"
            or not standalone_addon.independently_sellable
            or not standalone_addon.chargeable
            or (
                price_context.store_id is not None
                and standalone_addon.store_id != price_context.store_id
            )
        ):
            raise ValueError(
                f"confirmation standalone addon {item.get('addon_id')} is unavailable"
            )
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
            if price_context is not None and (
                project is None
                or project.publication_status != "published"
                or (
                    price_context.store_id is not None
                    and project.store_id != price_context.store_id
                )
            ):
                entity = "synthetic project" if isinstance(project_id, str) else "project"
                raise ValueError(f"confirmation {entity} {project_id} is unavailable")
            if project:
                prices = (
                    price_book_prices(db, project.id)
                    if price_context is not None
                    else _prices(db, project.id)
                )
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
            if price_context is not None and (
                addon is None
                or addon.publication_status != "published"
                or (
                    price_context.store_id is not None
                    and addon.store_id != price_context.store_id
                )
            ):
                raise ValueError(f"confirmation attached addon {addon_id} is unavailable")
            if price_context is not None and (
                project is None
                or not addon.can_attach_to_parent
                or (
                    addon.parent_project_id is not None
                    and addon.parent_project_id != project.id
                )
            ):
                raise ValueError(
                    f"confirmation attached addon {addon_id} is not applicable to project {project_id}"
                )
            if (
                not addon
                or addon.publication_status != "published"
                or (
                    project is not None
                    and addon.parent_project_id
                    and addon.parent_project_id != project.id
                )
            ):
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
        legacy_payable_unit = (
            base_member + addon_member
            if price_type == "member"
            else base_group + addon_store
            if price_type == "group"
            else base_store + addon_store
        )
        combined_prices = {
            "store": base_store + addon_store,
            "group": base_group + addon_store,
            "member": base_member + addon_member,
        }
        confirmed = (
            confirmed_price_for_line(
                combined_prices,
                price_context.is_member,
                price_context.confirmed_at,
                price_context.store_timezone,
                price_context.member_expire_at,
                price_context.member_type,
            )
            if price_context is not None
            else None
        )
        unit_payable = confirmed.amount_cents if confirmed is not None else legacy_payable_unit
        line_basis = confirmed.basis if confirmed is not None else price_type
        if price_context is not None:
            confirmation_payable_subtotal += unit_payable * quantity
        store_subtotal += line_store
        group_subtotal += line_group
        member_subtotal += line_member
        preferences = _preferences(item)
        item_code = _first_value(item, "code") or code
        unit_key = _bundle_unit_key(item, index)
        if (
            item_code == PROMO_FOOT_BATH_CODE
            and _has_bundle_base_eligibility(item)
            and unit_key not in seen_bundle_service_lines
        ):
            # 减免只免泡脚项目本身的基础价，泡脚上另加的小项照常收费（与顾客端预览口径一致）。
            legacy_confirmed_base = _confirmed_base_price(item)
            confirmed_base = (
                confirmed_price_for_line(
                    {"store": base_store, "group": base_group, "member": base_member},
                    price_context.is_member,
                    price_context.confirmed_at,
                    price_context.store_timezone,
                    price_context.member_expire_at,
                    price_context.member_type,
                )
                if price_context is not None
                else None
            )
            foot_bath_units.append((
                legacy_confirmed_base if legacy_confirmed_base is not None else base_store,
                legacy_confirmed_base if legacy_confirmed_base is not None else base_group,
                legacy_confirmed_base if legacy_confirmed_base is not None else base_member,
                confirmed_base.amount_cents if confirmed_base is not None else None,
            ))
            seen_bundle_service_lines.add(unit_key)
        if (
            _counts_for_foot_bath_bundle(item, code)
            and unit_key not in seen_bundle_service_lines
        ):
            part = _normalized_bundle_part(preferences)
            project_key = str(project.id) if project is not None else str(item_code)
            local_bundle_units.append((project_key, part))
            seen_bundle_service_lines.add(unit_key)
            if part:
                local_parts.add(part)
        pricing_line = {
            "line_index": index,
            "project_id": project_id,
            "addon_id": item.get("addon_id"),
            "item_kind": item.get("item_kind", "project"),
            "name": item.get("name", project.name if project else standalone_addon.name if standalone_addon else "局部加强"),
            "quantity": quantity,
            "unit_store_price_cents": base_store + addon_store,
            "unit_group_price_cents": base_group + addon_store,
            "unit_member_price_cents": base_member + addon_member,
            "price_basis": line_basis,
            "unit_payable_price_cents": unit_payable,
            "store_line_total_cents": line_store,
            "group_line_total_cents": line_group,
            "member_line_total_cents": line_member,
            "payable_line_total_cents": unit_payable * quantity,
            "addon_store_total_cents": addon_store * quantity,
            "addon_member_total_cents": addon_member * quantity,
        }
        service_line_id = _first_value(item, "service_line_id")
        if service_line_id is not None and str(service_line_id).strip():
            pricing_line["service_line_id"] = str(service_line_id).strip()
        lines.append(pricing_line)

    qualified_local_units = _qualified_local_bundle_unit_count(local_bundle_units)
    matched_foot_baths = min(len(foot_bath_units), qualified_local_units // 2)
    qualified = matched_foot_baths > 0
    # 两项合格局部调理匹配一个泡脚单位；只免泡脚项目本身的基础价，不免 addon/升级。
    adjustment_store = -sum(unit[0] for unit in foot_bath_units[:matched_foot_baths])
    adjustment_group = -sum(unit[1] for unit in foot_bath_units[:matched_foot_baths])
    adjustment_member = -sum(unit[2] for unit in foot_bath_units[:matched_foot_baths])
    payable_adjustment = (
        -sum(unit[3] for unit in foot_bath_units[:matched_foot_baths] if unit[3] is not None)
        if price_context is not None
        else {"store": adjustment_store, "group": adjustment_group, "member": adjustment_member}[price_type]
    )
    payable_subtotal = (
        confirmation_payable_subtotal
        if price_context is not None
        else {"store": store_subtotal, "group": group_subtotal, "member": member_subtotal}[price_type]
    )
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
        "payable_total_cents": max(0, payable_subtotal + payable_adjustment),
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


def _bundle_unit_key(item: dict, index: int) -> tuple[str, str | int]:
    service_line_id = _first_value(item, "service_line_id")
    if service_line_id is not None and str(service_line_id).strip():
        return ("service_line", str(service_line_id).strip())
    # 兼容旧输入：每一行至多是一个独立单位，quantity 永不扩展组合资格。
    return ("input_row", index)


def _normalized_bundle_part(preferences: list[str]) -> str | None:
    if not preferences:
        return None
    value = unicodedata.normalize("NFKC", preferences[0])
    normalized = "".join(value.split()).casefold()
    return normalized or None


def _qualified_local_bundle_unit_count(units: list[tuple[str, str | None]]) -> int:
    """同一局部项目的重复行只有不同且非空部位才能扩展为多个服务单位。"""
    by_project: dict[str, list[str | None]] = {}
    for project_key, part in units:
        by_project.setdefault(project_key, []).append(part)
    count = 0
    for parts in by_project.values():
        non_empty = {part for part in parts if part}
        # 一个局部项目可以作为一个单位；重复同项目则仅由不同的非空规范化部位扩展。
        count += max(1, len(non_empty))
    return count


def _confirmed_base_price(item: dict) -> int | None:
    value = _first_value(item, "confirmed_base_price_cents")
    return int(value) if value is not None else None


def _explicit_bundle_qualification(item: dict) -> bool | None:
    value = _first_value(item, "qualifies_for_foot_bath_bundle")
    if value is not None:
        return bool(value)
    return None


def _counts_for_foot_bath_bundle(item: dict, resolved_code: str | None = None) -> bool:
    if not _has_bundle_base_eligibility(item):
        return False
    explicit = _explicit_bundle_qualification(item)
    if explicit is not None:
        return explicit
    code = _first_value(item, "code") or resolved_code
    preferences = _preferences(item)
    return code == "hxy-jubu-30" and bool(preferences)


def _has_bundle_base_eligibility(item: dict) -> bool:
    state = _first_value(item, "state")
    if state not in BUNDLE_CONFIRMED_STATES:
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
    return True
