from pydantic import BaseModel


class LoginRequest(BaseModel):
    code: str  # wx.login 返回的 code


class BindPhoneRequest(BaseModel):
    code: str  # getPhoneNumber 返回的 code


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
