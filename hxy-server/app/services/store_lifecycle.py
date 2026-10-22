"""Store lifecycle guards shared by customer-facing transaction endpoints."""

from fastapi import HTTPException

from app.models import Store

OPEN_STORE_STATUSES = frozenset({"open", "trial_open"})
STORE_STATUS_LABELS = {
    "draft": "未建档",
    "preparing": "筹备中",
    "trial_open": "试营业",
    "open": "营业中",
    "suspended": "暂停营业",
    "closed": "已停业",
}


def require_store_open(store: Store | None, action: str = "到店服务") -> Store:
    """Reject new customer business when a store is not accepting orders.

    Existing orders are deliberately not touched here: a store suspension must
    stop new demand without invalidating service that is already in progress.
    """
    if store is None:
        raise HTTPException(status_code=404, detail="门店不存在")
    if store.status not in OPEN_STORE_STATUSES:
        label = STORE_STATUS_LABELS.get(store.status, store.status)
        raise HTTPException(
            status_code=409,
            detail={
                "code": "STORE_NOT_OPEN",
                "message": f"门店当前为「{label}」，暂不可{action}",
                "store_status": store.status,
            },
        )
    return store
