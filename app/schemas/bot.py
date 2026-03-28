from pydantic import BaseModel, Field


class TelegramLinkRequest(BaseModel):
    telegram_user_id: str = Field(
        ..., description="Telegram user id in format tg_<numeric_id>"
    )


class TelegramLinkResponse(BaseModel):
    user_id: str
    telegram_user_id: str
    linked: bool = True


class TelegramUnlinkResponse(BaseModel):
    user_id: str
    unlinked: bool = True


class TelegramPairApproveRequest(BaseModel):
    code: str = Field(..., min_length=4, max_length=32)


class TelegramPairApproveResponse(BaseModel):
    user_id: str
    telegram_user_id: str
    paired: bool = True


class TelegramSpendingAlertRequest(BaseModel):
    amount: float = Field(..., gt=0)
    threshold: float = Field(..., gt=0)
    category: str | None = None


class TelegramSpendingAlertResponse(BaseModel):
    user_id: str
    telegram_user_id: str
    alert_sent: bool
    reason: str
