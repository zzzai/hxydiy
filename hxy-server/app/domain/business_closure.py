from dataclasses import dataclass, replace


class BusinessClosureError(ValueError):
    """营业闭环规则拒绝当前动作。"""


class StateConflict(BusinessClosureError):
    code = "OPERATION_STATE_CONFLICT"


class ResourceBusy(BusinessClosureError):
    code = "RESOURCE_BUSY"


@dataclass(frozen=True, slots=True)
class BusinessClosureState:
    order: str
    visit: str
    service_order: str
    technician: str
    room: str


def _is_post_state(state: BusinessClosureState, action: str) -> bool:
    expected = {
        "assign": {
            "visit": "assigned",
            "service_order": "assigned",
            "technician": "reserved",
            "room": "reserved",
        },
        "ready": {"service_order": "ready", "room": "occupied"},
        "start_service": {
            "order": "in_service",
            "visit": "in_service",
            "service_order": "in_service",
            "technician": "in_service",
            "room": "in_service",
        },
        "finish_service": {
            "order": "pending_checkout",
            "visit": "pending_checkout",
            "service_order": "pending_checkout",
            "technician": "available",
            "room": "pending_checkout",
        },
        "settle": {
            "order": "completed",
            "visit": "completed",
            "service_order": "completed",
            "technician": "available",
            "room": "cleaning",
        },
        "finish_cleaning": {"room": "available"},
    }.get(action)
    return bool(expected) and all(getattr(state, key) == value for key, value in expected.items())


def _conflict(action: str, state: BusinessClosureState) -> StateConflict:
    return StateConflict(
        f"action {action} is not allowed for "
        f"order={state.order}, visit={state.visit}, service_order={state.service_order}, "
        f"technician={state.technician}, room={state.room}"
    )


def apply_action(
    state: BusinessClosureState,
    action: str,
    *,
    replay: bool = False,
) -> BusinessClosureState:
    """原子计算一个营业动作影响的全部状态。"""

    if replay and _is_post_state(state, action):
        return state

    if _is_post_state(state, action):
        raise _conflict(action, state)

    if action == "assign":
        if state.technician != "available":
            raise ResourceBusy(f"technician is {state.technician}")
        if state.room != "available":
            raise ResourceBusy(f"room is {state.room}")
        if not (
            state.order == "checked_in"
            and state.visit == "waiting_assignment"
            and state.service_order == "draft"
        ):
            raise _conflict(action, state)
        return replace(
            state,
            visit="assigned",
            service_order="assigned",
            technician="reserved",
            room="reserved",
        )

    if action == "ready":
        if not (
            state.visit == "assigned"
            and state.service_order == "assigned"
            and state.technician == "reserved"
            and state.room == "reserved"
        ):
            raise _conflict(action, state)
        return replace(state, service_order="ready", room="occupied")

    if action == "start_service":
        if not (
            state.order == "checked_in"
            and state.visit == "assigned"
            and state.service_order in {"assigned", "ready"}
            and state.technician == "reserved"
            and state.room in {"reserved", "occupied"}
        ):
            raise _conflict(action, state)
        return BusinessClosureState(
            order="in_service",
            visit="in_service",
            service_order="in_service",
            technician="in_service",
            room="in_service",
        )

    if action == "add_service":
        if state.service_order != "in_service":
            raise _conflict(action, state)
        return state

    if action == "finish_service":
        if not (
            state.order == "in_service"
            and state.visit == "in_service"
            and state.service_order == "in_service"
            and state.technician == "in_service"
            and state.room == "in_service"
        ):
            raise _conflict(action, state)
        return BusinessClosureState(
            order="pending_checkout",
            visit="pending_checkout",
            service_order="pending_checkout",
            technician="available",
            room="pending_checkout",
        )

    if action == "settle":
        if not (
            state.order == "pending_checkout"
            and state.visit == "pending_checkout"
            and state.service_order == "pending_checkout"
            and state.technician == "available"
            and state.room == "pending_checkout"
        ):
            raise _conflict(action, state)
        return BusinessClosureState(
            order="completed",
            visit="completed",
            service_order="completed",
            technician="available",
            room="cleaning",
        )

    if action == "finish_cleaning":
        if not (
            state.order == "completed"
            and state.visit == "completed"
            and state.service_order == "completed"
            and state.technician == "available"
            and state.room == "cleaning"
        ):
            raise _conflict(action, state)
        return replace(state, room="available")

    raise StateConflict(f"unknown action {action}")
