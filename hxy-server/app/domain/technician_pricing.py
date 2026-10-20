"""Read-only price projection shared by the technician task endpoints.

`SelectionSession.pricing_snapshot` is the persisted source of truth. This
module only normalizes that snapshot for display; it never recalculates,
mutates or persists prices, and it never exposes customer data.
"""

from app.models import SelectionSession

PRICE_TYPES = {"store", "member", "group"}
LINE_PRICE_KEYS = (
    "unit_store_price_cents",
    "unit_member_price_cents",
    "store_line_total_cents",
    "member_line_total_cents",
)


def price_cents(value) -> int | None:
    """Normalize one persisted cent value; bool/None/garbage becomes None."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return None


def _has_price_evidence(session: SelectionSession, snapshot: dict, raw_lines: list) -> bool:
    """Whether the session carries persisted price data worth showing.

    A snapshot that only contains metadata (or no snapshot at all) must not be
    rendered as a fake ¥0, so callers can fall back to "—" instead.
    """
    if not snapshot:
        return False
    for raw in raw_lines:
        if isinstance(raw, dict) and any(price_cents(raw.get(key)) is not None for key in LINE_PRICE_KEYS):
            return True
    for value in (
        session.store_total_cents,
        session.member_total_cents,
        snapshot.get("store_total_cents"),
        snapshot.get("member_total_cents"),
    ):
        if price_cents(value):
            return True
    return False


def selection_pricing(session: SelectionSession | None, *, require_snapshot: bool = False) -> dict | None:
    """Return the persisted price snapshot without exposing customer data.

    The technician views need both member and non-member totals;
    `applied_price_type` only tells the UI which one was recorded, not what the
    other one was. With ``require_snapshot=True`` (used by /my-tasks) a session
    without any persisted price evidence returns ``None`` instead of zero
    totals, so the UI can show "—" rather than a misleading ¥0.
    """
    if session is None:
        return None
    snapshot = session.pricing_snapshot if isinstance(session.pricing_snapshot, dict) else {}
    raw_lines = snapshot.get("lines") if isinstance(snapshot.get("lines"), list) else []
    if require_snapshot and not _has_price_evidence(session, snapshot, raw_lines):
        return None
    lines = []
    for index, raw in enumerate(raw_lines):
        if not isinstance(raw, dict):
            continue
        quantity = price_cents(raw.get("quantity"))
        quantity = max(1, quantity or 1)
        unit_store = price_cents(raw.get("unit_store_price_cents"))
        unit_member = price_cents(raw.get("unit_member_price_cents"))
        store_line = price_cents(raw.get("store_line_total_cents"))
        member_line = price_cents(raw.get("member_line_total_cents"))
        if store_line is None and unit_store is not None:
            store_line = unit_store * quantity
        if member_line is None and unit_member is not None:
            member_line = unit_member * quantity
        lines.append({
            "line_index": price_cents(raw.get("line_index")) if raw.get("line_index") is not None else index,
            "name": raw.get("name") if isinstance(raw.get("name"), str) else "",
            "quantity": quantity,
            "unit_store_price_cents": unit_store,
            "unit_member_price_cents": unit_member,
            "store_line_total_cents": store_line,
            "member_line_total_cents": member_line,
        })

    store_total = price_cents(session.store_total_cents)
    member_total = price_cents(session.member_total_cents)
    if not store_total:
        store_total = price_cents(snapshot.get("store_total_cents"))
    if not member_total:
        member_total = price_cents(snapshot.get("member_total_cents"))
    if store_total is None and lines:
        store_total = sum(line["store_line_total_cents"] or 0 for line in lines)
    if member_total is None and lines:
        member_total = sum(line["member_line_total_cents"] or 0 for line in lines)
    store_total = store_total or 0
    member_total = member_total or 0
    applied = snapshot.get("applied_price_type")
    if applied not in PRICE_TYPES:
        applied = None
    return {
        "store_total_cents": store_total,
        "member_total_cents": member_total,
        "member_saving_cents": max(0, store_total - member_total),
        "applied_price_type": applied,
        "lines": lines,
    }
