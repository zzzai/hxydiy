from pydantic import BaseModel
from pydantic import Field


class LoginRequest(BaseModel):
    code: str  # wx.login 返回的 code


class BindPhoneRequest(BaseModel):
    code: str  # getPhoneNumber 返回的 code


class H5SendCodeRequest(BaseModel):
    phone: str = Field(min_length=11, max_length=11)


class H5LoginRequest(BaseModel):
    phone: str = Field(min_length=11, max_length=11)
    code: str = Field(min_length=6, max_length=6)
    selection_session_id: str | None = Field(default=None, max_length=36)


class UserOut(BaseModel):
    id: int
    openid: str
    nickname: str = ""
    phone: str = ""
    is_member: bool = False
    member_type: str | None = None
    balance_cents: int = 0

    model_config = {"from_attributes": True}


class LoginResponse(BaseModel):
    token: str
    user: UserOut


class H5SendCodeResponse(BaseModel):
    sent: bool
    expires_in_seconds: int
    debug_code: str | None = None
