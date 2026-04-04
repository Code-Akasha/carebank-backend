from pydantic import BaseModel
from datetime import datetime


class TransactionBase(BaseModel):
    amount: float
    merchant: str | None = None
    category: str | None = None
    description: str | None = None


class TransactionCreate(TransactionBase):
    user_id: str


class TransactionTriggerCreate(TransactionBase):
    pass


class TransactionResponse(TransactionBase):
    id: int
    user_id: str
    date: datetime

    model_config = {"from_attributes": True}


class BalanceResponse(BaseModel):
    id: int
    user_id: str
    current_balance: float
    available_balance: float
    last_updated: datetime

    model_config = {"from_attributes": True}


class ProductBase(BaseModel):
    name: str
    type: str
    provider_id: str | None = None
    description: str | None = None
    min_balance_required: float | None = None
    interest_rate: float | None = None
    eligibility_rules: dict | None = None


class ProductResponse(ProductBase):
    id: int

    model_config = {"from_attributes": True}


class HealthScoreResponse(BaseModel):
    score: float
    factors: dict


class AccountResponse(BaseModel):
    account_id: str
    user_id: str
    provider_id: str
    name: str
    account_type: str
    mask: str | None = None
    currency: str | None = None
    institution: str | None = None
    current_balance: float
    available_balance: float | None = None
    status: str | None = None
    last_statement_date: str | None = None
    metadata_json: dict | None = None

    model_config = {"from_attributes": True}


class ProviderResponse(BaseModel):
    id: str
    name: str
    status: str | None = None
    country: str | None = None
    channels: list[str] | None = None
    latency_ms: int | None = None
    logo_url: str | None = None
    support_contact: str | None = None
    metadata_json: dict | None = None

    model_config = {"from_attributes": True}
