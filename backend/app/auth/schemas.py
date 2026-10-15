"""Request models for /auth. `extra='forbid'` blocks mass-assignment (e.g. sneaking {"role":"admin"} into sign-up) and
every field has a hard length cap so oversized inputs never reach the hasher or the database."""
from pydantic import BaseModel, ConfigDict, Field

HEX32 = r"^[0-9a-f]{32}$"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class CaptchaFields(Strict):
    captcha_id: str = Field(pattern=HEX32)
    captcha_answer: str = Field(min_length=1, max_length=10)


class SignupIn(CaptchaFields):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)
    full_name: str = Field(min_length=1, max_length=100)


class LoginIn(CaptchaFields):
    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class VerifyIn(Strict):
    challenge_id: str = Field(pattern=HEX32)
    code: str = Field(pattern=r"^\d{6}$")


class ResendIn(Strict):
    challenge_id: str = Field(pattern=HEX32)


class ForgotIn(CaptchaFields):
    email: str = Field(min_length=1, max_length=254)


class ResetIn(Strict):
    token: str = Field(pattern=r"^[A-Za-z0-9_-]{30,100}$")
    new_password: str = Field(min_length=1, max_length=128)


class ChangePasswordIn(Strict):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=1, max_length=128)
