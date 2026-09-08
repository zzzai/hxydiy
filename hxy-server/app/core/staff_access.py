"""普通员工在管理后台的最小只读访问边界。"""

from contextvars import ContextVar, Token


_request_scope: ContextVar[tuple[str, str] | None] = ContextVar("staff_request_scope", default=None)

_STAFF_READ_ONLY_ENDPOINTS = {
    ("GET", "/api/v1/admin/today-appointments"),
    ("GET", "/api/v1/admin/live-service-position-map"),
    ("GET", "/api/v1/admin/v2/selection-sessions"),
}


def bind_staff_request_scope(method: str, path: str) -> Token:
    return _request_scope.set((method.upper(), path))


def reset_staff_request_scope(token: Token) -> None:
    _request_scope.reset(token)


def staff_read_only_request_allowed() -> bool:
    """Only the PRD-approved store-operation read endpoints are available to staff."""
    method_and_path = _request_scope.get()
    if method_and_path in _STAFF_READ_ONLY_ENDPOINTS:
        return True
    if method_and_path is None:
        return False
    method, path = method_and_path
    return method == "GET" and path.startswith("/api/v1/admin/service-positions/") and path.endswith("/qr-link")
