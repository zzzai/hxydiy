import logging

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.wecom_staff import ATTEMPT_TTL, CALLBACK_PATH, COOKIE_PATH, WecomProvider, attempt_cookie, begin_attempt, complete_callback, configured_urls, exchange_attempt, get_wecom_provider


class CallbackAccessLogFilter(logging.Filter):
    def filter(self, record):
        if isinstance(record.args, tuple) and len(record.args) >= 3 and isinstance(record.args[2], str) and record.args[2].split("?", 1)[0].rstrip("/") == CALLBACK_PATH:
            args = list(record.args)
            args[2] = CALLBACK_PATH
            record.args = tuple(args)
        return True


logging.getLogger("uvicorn.access").addFilter(CallbackAccessLogFilter())
router = APIRouter(prefix="/auth/wecom", tags=["wecom-staff"])


class AuthorizeRequest(BaseModel):
    entry_nonce: str = Field(min_length=32, max_length=256)


class ExchangeRequest(AuthorizeRequest):
    attempt_id: str = Field(min_length=36, max_length=36)


@router.post("/authorize")
def authorize(body: AuthorizeRequest, response: Response, db: Session = Depends(get_db)):
    attempt, browser, url = begin_attempt(db, body.entry_nonce)
    response.set_cookie(attempt_cookie(attempt.id), browser, max_age=ATTEMPT_TTL, httponly=True, secure=True, samesite="lax", path=COOKIE_PATH)
    response.headers["Cache-Control"] = "no-store"
    return {"attempt_id": attempt.id, "authorization_url": url, "expires_in": ATTEMPT_TTL}


@router.get("/callback")
@router.get("/callback/", include_in_schema=False)
def callback(request: Request, code: str = "", state: str = "", db: Session = Depends(get_db), provider: WecomProvider = Depends(get_wecom_provider)):
    _, complete = configured_urls()
    complete_callback(db, state, code, request.cookies, provider)
    return RedirectResponse(complete, status_code=303, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


@router.post("/exchange")
def exchange(body: ExchangeRequest, request: Request, response: Response, db: Session = Depends(get_db), provider: WecomProvider = Depends(get_wecom_provider)):
    result = exchange_attempt(db, body.attempt_id, body.entry_nonce, request.cookies, provider)
    response.delete_cookie(attempt_cookie(body.attempt_id), path=COOKIE_PATH, secure=True, httponly=True, samesite="lax")
    response.headers["Cache-Control"] = "no-store"
    return result
