from pydantic import BaseModel, Field


class PersistentExpenseItem(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    amount: float = Field(ge=0)
    day_of_month: int = Field(ge=1, le=31)
    category: str = Field(default="other", min_length=1, max_length=50)


class UserProfileUpsertRequest(BaseModel):
    monthly_salary: float = Field(ge=0, default=0)
    currency: str = Field(default="INR", min_length=3, max_length=6)
    min_safe_balance: float = Field(ge=0, default=5000)
    savings_goal_pct: float = Field(ge=0, le=1, default=0.2)
    risk_tolerance: str = Field(default="moderate", min_length=3, max_length=30)
    persistent_expenses: list[PersistentExpenseItem] = Field(default_factory=list)
    notes: str | None = Field(default=None, max_length=1000)


class UserProfileResponse(BaseModel):
    user_id: str
    monthly_salary: float
    currency: str
    min_safe_balance: float
    savings_goal_pct: float
    risk_tolerance: str
    persistent_expenses: list[PersistentExpenseItem]
    total_persistent_expenses: float
    projected_free_cashflow: float
    notes: str | None = None

    model_config = {"from_attributes": True}
