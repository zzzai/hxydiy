"""Customer-only health report consent and bounded personal report access."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.customer_auth import current_customer_id
from app.domain.customer_phone_proof import phone_digest, verified_report_user
from app.models import AuditLog, CustomerProfileConsent, User
from app.schemas.tcm_reports import CONSENT_VERSION, ReportConsentIn, ReportConsentOut, ReportDetail, ReportList
from app.services.tcm_reports import read_report_source


router = APIRouter(prefix="/me", tags=["personal-health-reports"])
CONSENT_TYPE = "tcm_report_access"


def owner(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    return verified_report_user(authorization, db)


def consent_owner(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    # Withdrawal must remain available even when phone proof no longer matches.
    try:
        return db.get(User, current_customer_id(authorization, db))
    except (TypeError, ValueError, KeyError):
        raise HTTPException(401, "请重新登录") from None


def consent(db, user):
    return db.scalar(select(CustomerProfileConsent).where(
        CustomerProfileConsent.customer_id == user.id,
        CustomerProfileConsent.consent_type == CONSENT_TYPE,
        CustomerProfileConsent.consent_text_version == CONSENT_VERSION,
        CustomerProfileConsent.status == "active",
        CustomerProfileConsent.revoked_at.is_(None),
        CustomerProfileConsent.scope_json["phone_sha256"].as_string() == phone_digest(user.phone),
        (CustomerProfileConsent.expires_at.is_(None) | (CustomerProfileConsent.expires_at > datetime.now(timezone.utc))),
    ).order_by(CustomerProfileConsent.id.desc()))


def require_consent(db, user):
    if consent(db, user) is None:
        raise HTTPException(403, detail={"code": "TCM_CONSENT_REQUIRED", "message": "请先单独同意查看本人检测报告"})


def reject_unknown_query(request, allowed):
    if any(key not in allowed or len(request.query_params.getlist(key)) != 1 for key in request.query_params):
        raise HTTPException(422, "不接受手机号或其他身份覆盖参数")


@router.get("/tcm-report-consent", response_model=ReportConsentOut)
def consent_status(request: Request, user: User = Depends(owner), db: Session = Depends(get_db)):
    reject_unknown_query(request, set())
    return ReportConsentOut(consented=consent(db, user) is not None)


@router.post("/tcm-report-consent", response_model=ReportConsentOut)
def grant(request: Request, body: ReportConsentIn, user: User = Depends(owner), db: Session = Depends(get_db)):
    reject_unknown_query(request, set())
    db.scalar(select(User).where(User.id == user.id).with_for_update())
    if consent(db, user) is None:
        db.add(CustomerProfileConsent(customer_id=user.id, consent_type=CONSENT_TYPE,
            purpose="向已验证手机号持有人展示本人检测报告", data_categories_json=["health_detection_report"],
            scope_json={"phone_sha256": phone_digest(user.phone), "audience": "self"},
            consent_method="explicit_customer_action", consent_text_version=body.version,
            granted_at=datetime.now(timezone.utc), status="active"))
        db.add(AuditLog(actor_type="customer", actor_id=str(user.id), action="tcm_report_consent_granted",
                       entity_type="user", entity_id=str(user.id), detail={"version": CONSENT_VERSION}))
        db.commit()
    return ReportConsentOut(consented=True)


@router.delete("/tcm-report-consent", response_model=ReportConsentOut)
def revoke(request: Request, user: User = Depends(consent_owner), db: Session = Depends(get_db)):
    reject_unknown_query(request, set())
    db.scalar(select(User).where(User.id == user.id).with_for_update())
    for record in db.scalars(select(CustomerProfileConsent).where(
        CustomerProfileConsent.customer_id == user.id, CustomerProfileConsent.consent_type == CONSENT_TYPE,
        CustomerProfileConsent.status == "active")):
        record.status, record.revoked_at = "revoked", datetime.now(timezone.utc)
    db.add(AuditLog(actor_type="customer", actor_id=str(user.id), action="tcm_report_consent_revoked",
                   entity_type="user", entity_id=str(user.id), detail={"version": CONSENT_VERSION}))
    db.commit()
    return ReportConsentOut(consented=False)


@router.get("/tcm-reports", response_model=ReportList)
def reports(request: Request, limit: int = Query(20, ge=1, le=20), offset: int = Query(0, ge=0, le=100000),
            user: User = Depends(owner), db: Session = Depends(get_db)):
    reject_unknown_query(request, {"limit", "offset"})
    require_consent(db, user)
    return read_report_source(user.phone, limit=limit, offset=offset)


@router.get("/tcm-reports/{report_id}", response_model=ReportDetail)
def report(request: Request, report_id: str = Path(pattern=r"^[\w-]{1,128}$"),
           user: User = Depends(owner), db: Session = Depends(get_db)):
    reject_unknown_query(request, set())
    require_consent(db, user)
    return read_report_source(user.phone, report_id=report_id)
