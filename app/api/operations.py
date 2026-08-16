import hashlib
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.admin import _current_staff
from app.db.session import get_db
from app.domain.business_closure import (
    BusinessClosureError,
    BusinessClosureState,
    apply_action,
)
from app.domain.automatic_coupon import mark_automatic_coupon_used, select_automatic_coupon
from app.models import Order, OrderEvent, PositionOccupancy, Project, SelectionRevision, SelectionSession, ServiceLine, SettlementAdjustment, User
from app.models.operations import Room, Technician
from app.models.service import ServiceAssignment, ServiceOrder, StateTransition, Visit
from app.domain.occupancy import audit_occupancy

router = APIRouter(prefix="/operations", tags=["operations"])

ACTIVE_ASSIGNMENT_STATUSES = {"assigned", "ready", "in_service"}


class ActionIn(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=64)
    reason: str = Field(default="", max_length=256)


class AssignIn(ActionIn):
    technician_id: int
    room_id: int
    project_ids: list[int] = Field(min_length=1)


class SettleIn(ActionIn):
    payment_method: str = Field(min_length=1, max_length=32)
    received_amount_cents: int = Field(ge=0)
    payment_reference: str = Field(default="", max_length=64)
    service_adjustment_cents: int = Field(default=0, ge=0)
    adjustment_reason_code: str = Field(default="", max_length=32)
    responsibility: str = Field(default="", max_length=24)


class RefundNoteIn(ActionIn):
    amount_cents: int = Field(gt=0)
    reason_code: str = Field(min_length=1, max_length=32)
    responsibility: str = Field(min_length=1, max_length=24)
    refund_reference: str = Field(default="", max_length=64)


class CounterCheckoutIn(ActionIn):
    payment_method: str = Field(min_length=1, max_length=32)
    received_amount_cents: int = Field(ge=0)
    payment_reference: str = Field(default="", max_length=64)


class VisitCheckInIn(ActionIn):
    customer_id: int | None = Field(default=None, ge=1)


def _store_id(staff) -> int:
    if not staff.store_id:
        raise HTTPException(status_code=403, detail="当前账号未绑定门店")
    return staff.store_id


def _owned(entity, store_id: int, detail: str):
    if not entity or entity.store_id != store_id:
        raise HTTPException(status_code=404, detail=detail)
    return entity


def _latest_confirmed_revision_for_update(
    db: Session,
    selection_session_id: str,
) -> SelectionRevision | None:
    return db.scalar(
        select(SelectionRevision)
        .where(
            SelectionRevision.selection_session_id == selection_session_id,
            SelectionRevision.state == "confirmed",
        )
        .order_by(SelectionRevision.revision_no.desc(), SelectionRevision.id.asc())
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def _selection_occupancy_for_update(
    db: Session,
    selection_session_id: str,
) -> PositionOccupancy | None:
    return db.scalar(
        select(PositionOccupancy)
        .where(PositionOccupancy.selection_session_id == selection_session_id)
        .order_by(PositionOccupancy.id.desc())
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def _active_service_lines_for_update(
    db: Session,
    selection_session_id: str,
) -> list[ServiceLine]:
    return list(db.scalars(
        select(ServiceLine)
        .where(
            ServiceLine.selection_session_id == selection_session_id,
            ServiceLine.state != "cancelled",
        )
        .order_by(ServiceLine.id.asc())
        .with_for_update()
        .execution_options(populate_existing=True)
    ))


def _require_exact_service_line_snapshot(snapshot: dict, lines: list[ServiceLine]) -> None:
    items = snapshot.get("items") if isinstance(snapshot, dict) else None
    if not isinstance(items, list):
        raise HTTPException(status_code=409, detail={
            "code": "SERVICE_LINE_SNAPSHOT_MISMATCH",
            "message": "确认快照缺少完整服务项",
        })
    expected_ids = [
        str(item.get("service_line_id") or "").strip()
        for item in items
        if isinstance(item, dict)
    ]
    actual_ids = [str(line.id) for line in lines]
    if not expected_ids or not actual_ids:
        raise HTTPException(status_code=409, detail={
            "code": "SERVICE_LINES_NOT_CONFIRMED",
            "message": "实际服务项尚未由前台确认",
        })
    if (
        len(expected_ids) != len(items)
        or any(not line_id for line_id in expected_ids)
        or len(set(expected_ids)) != len(expected_ids)
        or set(expected_ids) != set(actual_ids)
        or len(actual_ids) != len(set(actual_ids))
    ):
        raise HTTPException(status_code=409, detail={
            "code": "SERVICE_LINE_SNAPSHOT_MISMATCH",
            "message": "实际服务项与最新确认快照不一致",
        })


def _require_frozen_billing_snapshot(
    order: Order,
    service_order: ServiceOrder,
    snapshot: dict,
) -> None:
    pricing = snapshot.get("pricing") if isinstance(snapshot, dict) else None
    if not isinstance(pricing, dict) or "payable_total_cents" not in pricing:
        raise HTTPException(status_code=409, detail={
            "code": "CONFIRMED_PRICING_REQUIRED",
            "message": "选单缺少前台确认的冻结价格",
        })
    pricing_lines = pricing.get("lines")
    if not isinstance(pricing_lines, list) or not all(isinstance(line, dict) for line in pricing_lines):
        raise HTTPException(status_code=409, detail={
            "code": "FROZEN_BILLING_SNAPSHOT_MISMATCH",
            "message": "服务账单缺少完整冻结项目",
        })
    frozen_items = [dict(line) for line in pricing_lines]
    payable_total = int(pricing["payable_total_cents"])
    store_total = int(pricing.get("store_total_cents", payable_total))
    expected_discount = max(0, store_total - payable_total)
    if (
        order.items != frozen_items
        or int(order.total_amount_cents) != payable_total
        or int(order.pay_amount_cents) != payable_total
        or int(order.discount_cents) != expected_discount
        or service_order.items != frozen_items
        or int(service_order.total_amount_cents) != payable_total
    ):
        raise HTTPException(status_code=409, detail={
            "code": "FROZEN_BILLING_SNAPSHOT_MISMATCH",
            "message": "服务账单与最新确认冻结快照不一致",
        })


def _hash_request(action: str, body: BaseModel) -> str:
    raw = json.dumps(
        {"action": action, "body": body.model_dump()},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _replay_or_conflict(
    db: Session,
    store_id: int,
    action: str,
    body: BaseModel,
) -> tuple[dict | None, str]:
    request_hash = _hash_request(action, body)
    existing = db.scalar(select(StateTransition).where(
        StateTransition.store_id == store_id,
        StateTransition.idempotency_key == body.idempotency_key,
    ))
    if not existing:
        return None, request_hash
    if existing.action != action or existing.request_hash != request_hash:
        raise HTTPException(
            status_code=409,
            detail={"code": "IDEMPOTENCY_CONFLICT", "message": "幂等键已用于其他请求"},
        )
    return existing.result_snapshot, request_hash


def _record_transition(
    db: Session,
    *,
    store_id: int,
    staff,
    entity_type: str,
    entity_id: int,
    action: str,
    from_status: str,
    to_status: str,
    body: ActionIn,
    request_hash: str,
    before: dict,
    after: dict,
    result: dict,
) -> None:
    db.add(StateTransition(
        store_id=store_id,
        entity_type=entity_type,
        entity_id=str(entity_id),
        action=action,
        from_status=from_status,
        to_status=to_status,
        actor_type="staff",
        actor_id=str(staff.id),
        actor_role=staff.role,
        idempotency_key=body.idempotency_key,
        request_hash=request_hash,
        reason=body.reason,
        before_snapshot=before,
        after_snapshot=after,
        result_snapshot=result,
    ))


def _state(order, visit, service_order, technician, room) -> BusinessClosureState:
    return BusinessClosureState(
        order=order.status,
        visit=visit.status,
        service_order=service_order.status,
        technician=technician.status,
        room=room.status,
    )


def _apply(state: BusinessClosureState, action: str) -> BusinessClosureState:
    try:
        return apply_action(state, action)
    except BusinessClosureError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc


def _closure_for_service(db: Session, service_order_id: int, store_id: int):
    # 先用不加锁的列查询定位关联键；真正状态读取统一按
    # SelectionSession -> Revision -> Occupancy -> Order -> ServiceOrder 获取行锁。
    link = db.execute(
        select(
            ServiceOrder.order_id.label("order_id"),
            ServiceOrder.visit_id.label("visit_id"),
            Visit.selection_session_id.label("selection_session_id"),
        )
        .join(Visit, Visit.id == ServiceOrder.visit_id)
        .where(ServiceOrder.id == service_order_id)
    ).mappings().first()
    if not link:
        raise HTTPException(status_code=404, detail="服务单不存在")

    selection_authority = None
    if link["selection_session_id"]:
        session = _owned(
            db.scalar(
                select(SelectionSession)
                .where(SelectionSession.id == link["selection_session_id"])
                .with_for_update()
                .execution_options(populate_existing=True)
            ),
            store_id,
            "选单不存在",
        )
        revision = _latest_confirmed_revision_for_update(db, session.id)
        occupancy = _selection_occupancy_for_update(db, session.id)
        order = _owned(
            db.scalar(
                select(Order)
                .where(Order.id == link["order_id"])
                .with_for_update()
                .execution_options(populate_existing=True)
            ),
            store_id,
            "订单不存在",
        )
        service_order = _owned(
            db.scalar(
                select(ServiceOrder)
                .where(ServiceOrder.id == service_order_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            ),
            store_id,
            "服务单不存在",
        )
        visit = _owned(
            db.scalar(
                select(Visit)
                .where(Visit.id == link["visit_id"])
                .with_for_update()
                .execution_options(populate_existing=True)
            ),
            store_id,
            "到店记录不存在",
        )
        selection_authority = {
            "session": session,
            "revision": revision,
            "occupancy": occupancy,
        }
    else:
        service_order = _owned(
            db.scalar(
                select(ServiceOrder)
                .where(ServiceOrder.id == service_order_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            ),
            store_id,
            "服务单不存在",
        )
        visit = _owned(
            db.scalar(
                select(Visit)
                .where(Visit.id == service_order.visit_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            ),
            store_id,
            "到店记录不存在",
        )
        order = _owned(
            db.scalar(
                select(Order)
                .where(Order.id == service_order.order_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            ),
            store_id,
            "订单不存在",
        )
    assignment = db.scalar(
        select(ServiceAssignment)
        .where(
            ServiceAssignment.service_order_id == service_order.id,
            ServiceAssignment.status.in_(ACTIVE_ASSIGNMENT_STATUSES | {"completed"}),
        )
        .order_by(ServiceAssignment.id.desc())
        .with_for_update()
    )
    if not assignment:
        raise HTTPException(status_code=409, detail={
            "code": "OPERATION_STATE_CONFLICT", "message": "服务单尚未派钟",
        })
    technician = _owned(
        db.scalar(select(Technician).where(Technician.id == assignment.technician_id).with_for_update()),
        store_id,
        "技师不存在",
    )
    room = _owned(
        db.scalar(select(Room).where(Room.id == assignment.room_id).with_for_update()),
        store_id,
        "房间不存在",
    )
    return service_order, visit, order, assignment, technician, room, selection_authority


@router.get("/live-board")
def live_board(
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
):
    staff = _current_staff(authorization, db)
    store_id = _store_id(staff)
    active_statuses = {
        "waiting_assignment", "assigned", "in_service", "pending_checkout",
    }
    visits = list(db.scalars(
        select(Visit)
        .where(Visit.store_id == store_id, Visit.status.in_(active_statuses))
        .order_by(Visit.arrived_at, Visit.id)
    ))
    summary = {status: 0 for status in active_statuses}
    items = []
    for visit in visits:
        summary[visit.status] += 1
        order = db.get(Order, visit.order_id)
        service_order = db.scalar(select(ServiceOrder).where(ServiceOrder.visit_id == visit.id))
        assignment = None
        technician = None
        room = None
        if service_order:
            assignment = db.scalar(
                select(ServiceAssignment)
                .where(ServiceAssignment.service_order_id == service_order.id)
                .order_by(ServiceAssignment.id.desc())
            )
        if assignment:
            technician = db.get(Technician, assignment.technician_id)
            room = db.get(Room, assignment.room_id)
        items.append({
            "id": visit.id,
            "status": visit.status,
            "arrived_at": visit.arrived_at.isoformat() if visit.arrived_at else None,
            "order_id": order.id,
            "order_no": order.order_no,
            "user_id": order.user_id,
            "items": order.items or [],
            "pay_amount_cents": order.pay_amount_cents,
            "service_order_id": service_order.id if service_order else None,
            "service_order_status": service_order.status if service_order else None,
            "assignment_id": assignment.id if assignment else None,
            "assignment_status": assignment.status if assignment else None,
            "technician_id": technician.id if technician else None,
            "technician_name": technician.name if technician else "",
            "room_id": room.id if room else None,
            "room_name": room.name if room else "",
        })

    technicians = list(db.scalars(
        select(Technician).where(Technician.store_id == store_id).order_by(Technician.sort_order, Technician.id)
    ))
    rooms = list(db.scalars(
        select(Room).where(Room.store_id == store_id).order_by(Room.sort_order, Room.id)
    ))
    completed_room_assignments = {
        room_id for room_id in db.scalars(
            select(ServiceAssignment.room_id)
            .where(
                ServiceAssignment.room_id.in_([item.id for item in rooms]),
                ServiceAssignment.status == "completed",
            )
        )
    }
    return {
        "summary": summary,
        "visits": items,
        "resources": {
            "technicians": [{
                "id": item.id, "name": item.name, "status": item.status,
            } for item in technicians],
            "rooms": [{
                "id": item.id,
                "name": item.name,
                "status": item.status,
                "can_finish_cleaning": item.status == "cleaning" and item.id in completed_room_assignments,
            } for item in rooms],
        },
    }


@router.post("/orders/{order_id}/check-in")
def check_in(
    order_id: int,
    body: ActionIn,
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
):
    staff = _current_staff(authorization, db)
    store_id = _store_id(staff)
    replay, request_hash = _replay_or_conflict(db, store_id, "check_in", body)
    if replay is not None:
        return replay

    order = _owned(
        db.scalar(select(Order).where(Order.id == order_id).with_for_update()),
        store_id,
        "订单不存在",
    )
    if order.order_type != "service" or order.status not in {"paid", "confirmed"}:
        raise HTTPException(status_code=409, detail={
            "code": "OPERATION_STATE_CONFLICT",
            "message": f"订单状态 {order.status} 不可办理到店",
        })
    if db.scalar(select(Visit).where(Visit.order_id == order.id)):
        raise HTTPException(status_code=409, detail={
            "code": "OPERATION_STATE_CONFLICT", "message": "订单已存在到店记录",
        })

    old_status = order.status
    visit = Visit(
        store_id=store_id,
        order_id=order.id,
        user_id=order.user_id,
        status="waiting_assignment",
    )
    db.add(visit)
    db.flush()
    service_order = ServiceOrder(
        store_id=store_id,
        order_id=order.id,
        visit_id=visit.id,
        status="draft",
        items=list(order.items or []),
        total_amount_cents=order.pay_amount_cents,
    )
    db.add(service_order)
    db.flush()
    order.status = "checked_in"
    result = {
        "order_id": order.id,
        "order_status": order.status,
        "visit_id": visit.id,
        "visit_status": visit.status,
        "service_order_id": service_order.id,
        "service_order_status": service_order.status,
    }
    _record_transition(
        db, store_id=store_id, staff=staff, entity_type="order", entity_id=order.id,
        action="check_in", from_status=old_status, to_status=order.status,
        body=body, request_hash=request_hash,
        before={"order": old_status},
        after={"order": order.status, "visit": visit.status, "service_order": service_order.status},
        result=result,
    )
    db.add(OrderEvent(
        order_id=order.id,
        from_status=old_status,
        to_status=order.status,
        action="check_in",
        operator=staff.name,
        reason=body.reason,
        idempotency_key=body.idempotency_key,
    ))
    db.commit()
    return result


@router.post("/visits/check-in")
def check_in_visit(
    body: VisitCheckInIn,
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
):
    staff = _current_staff(authorization, db)
    store_id = _store_id(staff)
    replay, request_hash = _replay_or_conflict(db, store_id, "visit_check_in", body)
    if replay is not None:
        return replay

    visit = Visit(
        store_id=store_id,
        user_id=body.customer_id,
        source="walk_in",
        status="waiting_project",
    )
    db.add(visit)
    db.flush()
    result = {
        "visit_id": visit.id,
        "visit_status": visit.status,
        "source": visit.source,
        "customer_id": visit.user_id,
        "order_id": None,
        "service_order_id": None,
    }
    _record_transition(
        db,
        store_id=store_id,
        staff=staff,
        entity_type="visit",
        entity_id=visit.id,
        action="visit_check_in",
        from_status="",
        to_status=visit.status,
        body=body,
        request_hash=request_hash,
        before={},
        after={"visit": visit.status, "source": visit.source},
        result=result,
    )
    db.commit()
    return result


@router.post("/selection-sessions/{selection_session_id}/counter-checkout")
def counter_checkout_selection(
    selection_session_id: str,
    body: CounterCheckoutIn,
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
):
    """把前台已确认并冻结价格的 DIY 选单转成服务单，服务完成前不收款。"""
    staff = _current_staff(authorization, db)
    store_id = _store_id(staff)
    replay, request_hash = _replay_or_conflict(db, store_id, "counter_checkout_selection", body)
    if replay is not None:
        return replay

    session = _owned(
        db.scalar(
            select(SelectionSession)
            .where(SelectionSession.id == selection_session_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ),
        store_id,
        "选单不存在",
    )
    selection_from_status = session.status
    if session.status != "confirmed":
        raise HTTPException(status_code=409, detail={
            "code": "OPERATION_STATE_CONFLICT", "message": "选单须先由前台确认价格和服务项",
        })
    if session.fulfillment_order_id:
        raise HTTPException(status_code=409, detail={
            "code": "OPERATION_STATE_CONFLICT", "message": "该选单已转为服务单",
        })
    if not session.customer_id:
        anonymous = User(openid=f"counter_selection_{session.id}")
        db.add(anonymous)
        db.flush()
        session.customer_id = anonymous.id

    latest_revision = _latest_confirmed_revision_for_update(db, session.id)
    snapshot = (latest_revision.snapshot or {}) if latest_revision else {}
    pricing_snapshot = snapshot.get("pricing")
    if (
        latest_revision is None
        or not isinstance(pricing_snapshot, dict)
        or "payable_total_cents" not in pricing_snapshot
    ):
        raise HTTPException(status_code=409, detail={
            "code": "CONFIRMED_PRICING_REQUIRED", "message": "选单缺少前台确认的冻结价格",
        })
    payable_total = int(pricing_snapshot["payable_total_cents"] or 0)
    if payable_total < 0 or body.received_amount_cents < payable_total:
        raise HTTPException(status_code=409, detail={
            "code": "PAYMENT_NOT_CONFIRMED", "message": "实收金额低于本次选单参考金额",
        })
    occupancy = _selection_occupancy_for_update(db, session.id)
    if occupancy and occupancy.status not in {"waiting_service", "in_service", "post_service_present"}:
        raise HTTPException(status_code=409, detail={
            "code": "OPERATION_STATE_CONFLICT", "message": "当前服务位状态不能接待该选单",
        })

    from app.api.orders import gen_order_no

    priced_items = list(pricing_snapshot.get("lines") or snapshot.get("items") or [])
    confirmed_lines = _active_service_lines_for_update(db, session.id)
    _require_exact_service_line_snapshot(snapshot, confirmed_lines)
    order = Order(
        order_no=gen_order_no(),
        order_type="service",
        user_id=session.customer_id,
        store_id=store_id,
        items=priced_items,
        total_amount_cents=payable_total,
        discount_cents=max(0, int(pricing_snapshot.get("store_total_cents", payable_total) or payable_total) - payable_total),
        pay_amount_cents=payable_total,
        status="checked_in",
        pay_status="unpaid",
        pay_transaction_id="",
    )
    db.add(order)
    db.flush()
    visit = Visit(
        store_id=store_id,
        order_id=order.id,
        user_id=session.customer_id,
        source="diy_selection",
        selection_session_id=session.id,
        status="waiting_assignment",
    )
    db.add(visit)
    db.flush()
    service_order = ServiceOrder(
        store_id=store_id,
        order_id=order.id,
        visit_id=visit.id,
        status="draft",
        items=priced_items,
        total_amount_cents=payable_total,
    )
    db.add(service_order)
    db.flush()
    session.status = "confirmed"
    session.fulfillment_order_id = order.id
    result = {
        "selection_session_id": session.id,
        "selection_status": session.status,
        "order_id": order.id,
        "order_status": order.status,
        "visit_id": visit.id,
        "visit_status": visit.status,
        "service_order_id": service_order.id,
        "service_order_status": service_order.status,
        "payable_total_cents": payable_total,
        "payment_status": order.pay_status,
    }
    _record_transition(
        db, store_id=store_id, staff=staff, entity_type="selection_session", entity_id=session.id,
        action="counter_checkout_selection", from_status=selection_from_status, to_status=session.status,
        body=body, request_hash=request_hash,
        before={"selection_session": selection_from_status, "fulfillment_order_id": None},
        after={"selection_session": session.status, "order": order.status, "visit": visit.status, "service_order": service_order.status},
        result=result,
    )
    db.add(OrderEvent(
        order_id=order.id, from_status="", to_status=order.status,
        action="counter_checkout_selection", operator=staff.name, reason=body.reason,
        idempotency_key=body.idempotency_key,
    ))
    db.commit()
    return result


@router.post("/selection-sessions/{selection_session_id}/settle")
def settle_completed_selection(
    selection_session_id: str,
    body: SettleIn,
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
):
    """服务完成后按已确认 DIY 服务项登记线下收款。"""
    staff = _current_staff(authorization, db)
    store_id = _store_id(staff)
    replay, request_hash = _replay_or_conflict(db, store_id, "settle_completed_selection", body)
    if replay is not None:
        return replay

    session = _owned(
        db.scalar(
            select(SelectionSession)
            .where(SelectionSession.id == selection_session_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ),
        store_id,
        "选单不存在",
    )
    if session.status != "confirmed":
        raise HTTPException(status_code=409, detail={
            "code": "OPERATION_STATE_CONFLICT", "message": "只有已确认选单可以结算",
        })
    if session.fulfillment_order_id:
        raise HTTPException(status_code=409, detail={
            "code": "SELECTION_ALREADY_SETTLED", "message": "该选单已经完成结算",
        })
    latest_revision = _latest_confirmed_revision_for_update(db, session.id)
    snapshot = (latest_revision.snapshot or {}) if latest_revision else {}
    pricing = snapshot.get("pricing")
    if (
        latest_revision is None
        or not isinstance(pricing, dict)
        or "payable_total_cents" not in pricing
    ):
        raise HTTPException(status_code=409, detail={
            "code": "CONFIRMED_PRICING_REQUIRED",
            "message": "选单缺少前台确认的冻结价格",
        })
    occupancy = _selection_occupancy_for_update(db, session.id)
    abnormal_service = bool(
        occupancy
        and occupancy.status == "cleaning"
        and occupancy.actual_service_end_at
        and occupancy.release_reason
    )
    if not occupancy or (
        occupancy.status != "post_service_present" and not abnormal_service
    ) or not occupancy.actual_service_end_at:
        raise HTTPException(status_code=409, detail={
            "code": "SERVICE_NOT_COMPLETED", "message": "服务完成后才可以结算",
        })

    service_lines = _active_service_lines_for_update(db, session.id)
    _require_exact_service_line_snapshot(snapshot, service_lines)
    unfinished_lines = [line for line in service_lines if line.state != "completed"]
    if unfinished_lines and not abnormal_service:
        raise HTTPException(status_code=409, detail={
            "code": "SERVICE_LINES_NOT_COMPLETED", "message": "仍有服务项目未完成，不能结算",
        })
    if abnormal_service and (
        not body.adjustment_reason_code.strip()
        or not body.responsibility.strip()
        or not body.reason.strip()
    ):
        raise HTTPException(status_code=409, detail={
            "code": "SERVICE_ADJUSTMENT_REQUIRED",
            "message": "异常服务结算必须填写减免原因、责任归属和现场说明",
        })

    payable_total = int(pricing.get("payable_total_cents", session.store_total_cents) or 0)
    automatic_coupon = select_automatic_coupon(
        db,
        customer_id=session.customer_id,
        pricing=pricing,
        now=datetime.now(timezone.utc),
        lock=True,
    )
    payable_after_coupon = automatic_coupon.payable_after_coupon_cents
    if body.service_adjustment_cents > payable_after_coupon:
        raise HTTPException(status_code=409, detail={
            "code": "SERVICE_ADJUSTMENT_EXCEEDED", "message": "服务减免不能超过原应收金额",
        })
    final_payable_total = payable_after_coupon - body.service_adjustment_cents
    if body.received_amount_cents < final_payable_total:
        raise HTTPException(status_code=409, detail={
            "code": "PAYMENT_NOT_CONFIRMED", "message": "实收金额低于本次应收金额",
        })

    from app.api.orders import gen_order_no

    settlement_items = [
        {**line.snapshot, "settlement_state": line.state}
        for line in service_lines
    ]
    if automatic_coupon.coupon_id is not None:
        settlement_items.append(automatic_coupon.audit_item())
    order = Order(
        order_no=gen_order_no(),
        order_type="service",
        user_id=session.customer_id,
        store_id=store_id,
        items=settlement_items,
        coupon_id=automatic_coupon.coupon_id,
        total_amount_cents=payable_total,
        discount_cents=max(
            0,
            int(pricing.get("store_total_cents", payable_total) or payable_total) - final_payable_total,
        ),
        pay_amount_cents=final_payable_total,
        status="completed",
        pay_status="paid",
        pay_transaction_id=body.payment_reference,
    )
    db.add(order)
    db.flush()
    mark_automatic_coupon_used(db, automatic_coupon, order_id=order.id)
    if abnormal_service:
        for line in unfinished_lines:
            line.state = "cancelled"
        db.add(SettlementAdjustment(
            store_id=store_id,
            order_id=order.id,
            selection_session_id=session.id,
            adjustment_type="service_waiver",
            amount_cents=body.service_adjustment_cents,
            original_amount_cents=payable_after_coupon,
            final_amount_cents=final_payable_total,
            reason_code=body.adjustment_reason_code.strip(),
            reason=body.reason.strip(),
            responsibility=body.responsibility.strip(),
            payment_allocation={
                "payment_method": body.payment_method,
                "received_amount_cents": body.received_amount_cents,
                "payment_reference": body.payment_reference,
            },
            actor_staff_id=staff.id,
        ))
    session.fulfillment_order_id = order.id
    result = {
        "selection_session_id": session.id,
        "order_id": order.id,
        "order_status": order.status,
        "payment_status": order.pay_status,
        "original_payable_total_cents": payable_total,
        "payable_after_coupon_cents": payable_after_coupon,
        "automatic_coupon": automatic_coupon.as_dict(),
        "service_adjustment_cents": body.service_adjustment_cents,
        "payable_total_cents": final_payable_total,
        "received_amount_cents": body.received_amount_cents,
        "payment_method": body.payment_method,
    }
    _record_transition(
        db,
        store_id=store_id,
        staff=staff,
        entity_type="selection_session",
        entity_id=session.id,
        action="settle_completed_selection",
        from_status=session.status,
        to_status=session.status,
        body=body,
        request_hash=request_hash,
        before={"selection_session": session.status, "fulfillment_order_id": None},
        after={"selection_session": session.status, "fulfillment_order_id": order.id},
        result=result,
    )
    db.add(OrderEvent(
        order_id=order.id,
        from_status="pending_checkout",
        to_status=order.status,
        action="settle_completed_selection",
        operator=staff.name,
        reason=body.reason,
        idempotency_key=body.idempotency_key,
    ))
    db.commit()
    return result


@router.post("/orders/{order_id}/refund-note")
def register_refund_note(
    order_id: int,
    body: RefundNoteIn,
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
):
    """登记已在线下或第三方渠道完成的退款，不主动发起资金操作。"""
    staff = _current_staff(authorization, db)
    if staff.role != "admin":
        raise HTTPException(status_code=403, detail="退款登记需要管理员权限")
    store_id = _store_id(staff)
    replay, request_hash = _replay_or_conflict(db, store_id, "refund_note", body)
    if replay is not None:
        return replay

    order = _owned(
        db.scalar(select(Order).where(Order.id == order_id).with_for_update()),
        store_id,
        "订单不存在",
    )
    if order.pay_status not in {"paid", "refunded"}:
        raise HTTPException(status_code=409, detail={
            "code": "ORDER_NOT_PAID", "message": "只有已支付订单可以登记退款",
        })
    refunded_amount = sum(db.scalars(select(SettlementAdjustment.amount_cents).where(
        SettlementAdjustment.order_id == order.id,
        SettlementAdjustment.adjustment_type == "refund_note",
        SettlementAdjustment.status == "registered",
    )))
    next_refunded_amount = refunded_amount + body.amount_cents
    if next_refunded_amount > order.pay_amount_cents:
        raise HTTPException(status_code=409, detail={
            "code": "REFUND_AMOUNT_EXCEEDED", "message": "累计退款不能超过订单实付金额",
        })

    before_status = order.refund_status
    order.refund_status = (
        "refunded" if next_refunded_amount == order.pay_amount_cents else "partially_refunded"
    )
    if order.refund_status == "refunded":
        order.pay_status = "refunded"
    adjustment = SettlementAdjustment(
        store_id=store_id,
        order_id=order.id,
        selection_session_id=None,
        adjustment_type="refund_note",
        amount_cents=body.amount_cents,
        original_amount_cents=order.pay_amount_cents,
        final_amount_cents=order.pay_amount_cents - next_refunded_amount,
        reason_code=body.reason_code,
        reason=body.reason,
        responsibility=body.responsibility,
        payment_allocation={"refund_reference": body.refund_reference},
        actor_staff_id=staff.id,
    )
    db.add(adjustment)
    result = {
        "order_id": order.id,
        "refund_status": order.refund_status,
        "refunded_amount_cents": next_refunded_amount,
        "remaining_paid_amount_cents": order.pay_amount_cents - next_refunded_amount,
    }
    _record_transition(
        db,
        store_id=store_id,
        staff=staff,
        entity_type="order",
        entity_id=order.id,
        action="refund_note",
        from_status=before_status,
        to_status=order.refund_status,
        body=body,
        request_hash=request_hash,
        before={"refund_status": before_status, "refunded_amount_cents": refunded_amount},
        after={"refund_status": order.refund_status, "refunded_amount_cents": next_refunded_amount},
        result=result,
    )
    db.commit()
    return result


@router.post("/visits/{visit_id}/assign")
def assign(
    visit_id: int,
    body: AssignIn,
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
):
    staff = _current_staff(authorization, db)
    store_id = _store_id(staff)
    replay, request_hash = _replay_or_conflict(db, store_id, "assign", body)
    if replay is not None:
        return replay

    visit = _owned(
        db.scalar(select(Visit).where(Visit.id == visit_id).with_for_update()),
        store_id,
        "到店记录不存在",
    )
    service_order = db.scalar(
        select(ServiceOrder).where(ServiceOrder.visit_id == visit.id).with_for_update()
    )
    order = _owned(db.get(Order, visit.order_id), store_id, "订单不存在")
    technician = _owned(
        db.scalar(select(Technician).where(Technician.id == body.technician_id).with_for_update()),
        store_id,
        "技师不存在",
    )
    room = _owned(
        db.scalar(select(Room).where(Room.id == body.room_id).with_for_update()),
        store_id,
        "房间不存在",
    )
    diy_occupancy = db.scalar(select(PositionOccupancy).where(
        PositionOccupancy.active_room_id == room.id,
    ).with_for_update())
    if visit.selection_session_id:
        own_occupancy = db.scalar(select(PositionOccupancy).where(
            PositionOccupancy.active_session_id == visit.selection_session_id,
        ).with_for_update())
        if own_occupancy and own_occupancy.active_room_id != room.id:
            raise HTTPException(status_code=409, detail={
                "code": "DIY_POSITION_MISMATCH",
                "message": "DIY 选单必须在当前绑定的服务位派钟",
            })
    if diy_occupancy and diy_occupancy.selection_session_id != visit.selection_session_id:
        raise HTTPException(status_code=409, detail={
            "code": "DIY_POSITION_OCCUPIED",
            "message": "该服务位已有活动 DIY 选单，请选择其他服务位",
        })
    projects = list(db.scalars(select(Project).where(Project.id.in_(body.project_ids))))
    if len({project.id for project in projects}) != len(set(body.project_ids)) or any(
        project.store_id != store_id for project in projects
    ):
        raise HTTPException(status_code=404, detail="项目不存在")

    active = db.scalar(select(ServiceAssignment).where(
        ServiceAssignment.status.in_(ACTIVE_ASSIGNMENT_STATUSES),
        or_(
            ServiceAssignment.technician_id == technician.id,
            ServiceAssignment.room_id == room.id,
        ),
    ))
    if active:
        resource = "technician" if active.technician_id == technician.id else "room"
        raise HTTPException(status_code=409, detail={
            "code": "RESOURCE_BUSY", "message": f"{resource} is already assigned",
        })

    before = _state(order, visit, service_order, technician, room)
    after = _apply(before, "assign")
    visit.status = after.visit
    service_order.status = after.service_order
    technician.status = after.technician
    room.status = after.room
    room.current_tech = technician.name
    room.used_count = 1
    assignment = ServiceAssignment(
        store_id=store_id,
        service_order_id=service_order.id,
        technician_id=technician.id,
        room_id=room.id,
        project_ids=list(dict.fromkeys(body.project_ids)),
        status="assigned",
    )
    db.add(assignment)
    db.flush()
    result = {
        "visit_id": visit.id,
        "visit_status": visit.status,
        "service_order_id": service_order.id,
        "service_order_status": service_order.status,
        "assignment_id": assignment.id,
        "technician_status": technician.status,
        "room_status": room.status,
    }
    _record_transition(
        db, store_id=store_id, staff=staff, entity_type="visit", entity_id=visit.id,
        action="assign", from_status=before.visit, to_status=after.visit,
        body=body, request_hash=request_hash,
        before=before.__dict__ if hasattr(before, "__dict__") else {
            "order": before.order, "visit": before.visit, "service_order": before.service_order,
            "technician": before.technician, "room": before.room,
        },
        after={
            "order": after.order, "visit": after.visit, "service_order": after.service_order,
            "technician": after.technician, "room": after.room,
        },
        result=result,
    )
    db.commit()
    return result


def _service_action(
    service_order_id: int,
    body: ActionIn,
    action: str,
    authorization: str | None,
    db: Session,
):
    staff = _current_staff(authorization, db)
    store_id = _store_id(staff)
    replay, request_hash = _replay_or_conflict(db, store_id, action, body)
    if replay is not None:
        return replay

    service_order, visit, order, assignment, technician, room, selection_authority = _closure_for_service(
        db, service_order_id, store_id
    )
    before = _state(order, visit, service_order, technician, room)
    after = _apply(before, action)
    now = datetime.now(timezone.utc)
    order.status = after.order
    visit.status = after.visit
    service_order.status = after.service_order
    technician.status = after.technician
    room.status = after.room

    if action == "ready":
        assignment.status = "ready"
    elif action == "start_service":
        assignment.status = "in_service"
        assignment.started_at = now
        service_order.started_at = now
    elif action == "finish_service":
        assignment.status = "completed"
        assignment.finished_at = now
        service_order.finished_at = now
        room.current_tech = ""
    selection_session_id = visit.selection_session_id
    if selection_session_id and action in {"start_service", "finish_service"}:
        service_lines = _active_service_lines_for_update(db, selection_session_id)
        for line in service_lines:
            if action == "start_service" and line.state == "pending":
                line.state = "in_service"
                line.started_at = now
            elif action == "finish_service" and line.state in {"pending", "in_service"}:
                line.state = "completed"
                line.completed_at = now
    if selection_session_id and action in {"start_service", "finish_service"}:
        occupancy = selection_authority["occupancy"] if selection_authority else None
        if occupancy:
            occupancy_before = occupancy.status
            if action == "start_service" and occupancy.status == "waiting_service":
                occupancy.status = "in_service"
                occupancy.actual_start_at = now
                occupancy.version += 1
            elif action == "finish_service" and occupancy.status in {"waiting_service", "in_service"}:
                occupancy.status = "post_service_present"
                occupancy.actual_service_end_at = now
                occupancy.version += 1
            else:
                occupancy_before = ""
            if occupancy_before:
                audit_occupancy(db, occupancy, action, "staff", str(staff.id), {
                    "from_status": occupancy_before,
                    "to_status": occupancy.status,
                    "service_order_id": service_order.id,
                })
    result = {
        "service_order_id": service_order.id,
        "service_order_status": service_order.status,
        "visit_status": visit.status,
        "order_status": order.status,
        "assignment_status": assignment.status,
        "technician_status": technician.status,
        "room_status": room.status,
    }
    _record_transition(
        db, store_id=store_id, staff=staff, entity_type="service_order",
        entity_id=service_order.id, action=action,
        from_status=before.service_order, to_status=after.service_order,
        body=body, request_hash=request_hash,
        before={
            "order": before.order, "visit": before.visit, "service_order": before.service_order,
            "technician": before.technician, "room": before.room,
        },
        after={
            "order": after.order, "visit": after.visit, "service_order": after.service_order,
            "technician": after.technician, "room": after.room,
        },
        result=result,
    )
    db.commit()
    return result


@router.post("/service-orders/{service_order_id}/ready")
def ready_for_service(
    service_order_id: int,
    body: ActionIn,
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
):
    return _service_action(service_order_id, body, "ready", authorization, db)


@router.post("/service-orders/{service_order_id}/start")
def start_service(
    service_order_id: int,
    body: ActionIn,
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
):
    return _service_action(service_order_id, body, "start_service", authorization, db)


@router.post("/service-orders/{service_order_id}/finish")
def finish_service(
    service_order_id: int,
    body: ActionIn,
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
):
    return _service_action(service_order_id, body, "finish_service", authorization, db)


@router.post("/service-orders/{service_order_id}/settle")
def settle(
    service_order_id: int,
    body: SettleIn,
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
):
    staff = _current_staff(authorization, db)
    store_id = _store_id(staff)
    replay, request_hash = _replay_or_conflict(db, store_id, "settle", body)
    if replay is not None:
        return replay

    service_order, visit, order, assignment, technician, room, selection_authority = _closure_for_service(
        db, service_order_id, store_id
    )
    settlement_pricing = {
        "store_total_cents": order.total_amount_cents,
        "member_total_cents": order.pay_amount_cents,
        "payable_total_cents": order.pay_amount_cents,
    }
    coupon_customer_id = None
    if selection_authority:
        if selection_authority["session"].status != "confirmed":
            raise HTTPException(status_code=409, detail={
                "code": "OPERATION_STATE_CONFLICT",
                "message": "选单须保持前台确认状态才能线下结算",
            })
        latest_revision = selection_authority["revision"]
        if latest_revision is None:
            raise HTTPException(status_code=409, detail={
                "code": "CONFIRMED_PRICING_REQUIRED",
                "message": "选单缺少前台确认的冻结版本",
            })
        service_lines = _active_service_lines_for_update(
            db,
            selection_authority["session"].id,
        )
        _require_exact_service_line_snapshot(latest_revision.snapshot or {}, service_lines)
        _require_frozen_billing_snapshot(order, service_order, latest_revision.snapshot or {})
        settlement_pricing = latest_revision.snapshot["pricing"]
        coupon_customer_id = selection_authority["session"].customer_id
    now = datetime.now(timezone.utc)
    automatic_coupon = select_automatic_coupon(
        db,
        customer_id=coupon_customer_id if order.pay_status != "paid" else None,
        pricing=settlement_pricing,
        now=now,
        lock=True,
    )
    final_payable_total = automatic_coupon.payable_after_coupon_cents
    if order.pay_status != "paid" and body.received_amount_cents < final_payable_total:
        raise HTTPException(status_code=409, detail={
            "code": "PAYMENT_NOT_CONFIRMED", "message": "实收金额或支付状态尚未确认",
        })
    before = _state(order, visit, service_order, technician, room)
    after = _apply(before, "settle")
    if automatic_coupon.coupon_id is not None:
        order.items = [*list(order.items or []), automatic_coupon.audit_item()]
        order.coupon_id = automatic_coupon.coupon_id
        order.pay_amount_cents = final_payable_total
        order.discount_cents = max(
            0,
            int(settlement_pricing.get("store_total_cents", final_payable_total) or 0)
            - final_payable_total,
        )
        service_order.total_amount_cents = final_payable_total
        mark_automatic_coupon_used(db, automatic_coupon, order_id=order.id)
    order.status = after.order
    order.pay_status = "paid"
    if body.payment_reference:
        order.pay_transaction_id = body.payment_reference
    visit.status = after.visit
    visit.completed_at = now
    service_order.status = after.service_order
    service_order.settled_at = now
    technician.status = after.technician
    room.status = after.room
    result = {
        "service_order_id": service_order.id,
        "service_order_status": service_order.status,
        "visit_status": visit.status,
        "order_status": order.status,
        "assignment_status": assignment.status,
        "technician_status": technician.status,
        "room_status": room.status,
        "payment_method": body.payment_method,
        "received_amount_cents": body.received_amount_cents,
        "payable_total_cents": final_payable_total,
        "automatic_coupon": automatic_coupon.as_dict(),
    }
    _record_transition(
        db, store_id=store_id, staff=staff, entity_type="service_order",
        entity_id=service_order.id, action="settle",
        from_status=before.service_order, to_status=after.service_order,
        body=body, request_hash=request_hash,
        before={
            "order": before.order, "visit": before.visit, "service_order": before.service_order,
            "technician": before.technician, "room": before.room,
        },
        after={
            "order": after.order, "visit": after.visit, "service_order": after.service_order,
            "technician": after.technician, "room": after.room,
        },
        result=result,
    )
    db.commit()
    return result


@router.post("/rooms/{room_id}/finish-cleaning")
def finish_cleaning(
    room_id: int,
    body: ActionIn,
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
):
    staff = _current_staff(authorization, db)
    store_id = _store_id(staff)
    replay, request_hash = _replay_or_conflict(db, store_id, "finish_cleaning", body)
    if replay is not None:
        return replay

    room = _owned(
        db.scalar(select(Room).where(Room.id == room_id).with_for_update()),
        store_id,
        "房间不存在",
    )
    if db.scalar(select(PositionOccupancy).where(
        PositionOccupancy.active_room_id == room.id,
    ).with_for_update()):
        raise HTTPException(status_code=409, detail={
            "code": "DIY_POSITION_OCCUPIED",
            "message": "该服务位仍有活动 DIY 选单，请在服务位看板完成现场操作",
        })
    if db.scalar(select(ServiceAssignment).where(
        ServiceAssignment.room_id == room.id,
        ServiceAssignment.status.in_(ACTIVE_ASSIGNMENT_STATUSES),
    )):
        raise HTTPException(status_code=409, detail={
            "code": "RESOURCE_BUSY", "message": "房间仍有活动服务",
        })
    assignment = db.scalar(
        select(ServiceAssignment)
        .where(ServiceAssignment.room_id == room.id, ServiceAssignment.status == "completed")
        .order_by(ServiceAssignment.id.desc())
    )
    if not assignment:
        raise HTTPException(status_code=409, detail={
            "code": "OPERATION_STATE_CONFLICT", "message": "房间没有已完成服务",
        })
    service_order = db.get(ServiceOrder, assignment.service_order_id)
    visit = db.get(Visit, service_order.visit_id)
    order = db.get(Order, service_order.order_id)
    technician = db.get(Technician, assignment.technician_id)
    before = _state(order, visit, service_order, technician, room)
    after = _apply(before, "finish_cleaning")
    room.status = after.room
    room.used_count = 0
    room.current_tech = ""
    result = {"room_id": room.id, "room_status": room.status}
    _record_transition(
        db, store_id=store_id, staff=staff, entity_type="room", entity_id=room.id,
        action="finish_cleaning", from_status=before.room, to_status=after.room,
        body=body, request_hash=request_hash,
        before={"room": before.room}, after={"room": after.room}, result=result,
    )
    db.commit()
    return result
