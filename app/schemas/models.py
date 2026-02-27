from pydantic import BaseModel
from datetime import datetime


class TransactionBase(BaseModel):
    amount: float
    merchant: str
    category: str
    description: str | None = None


class TransactionCreate(TransactionBase):
    user_id: str


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
