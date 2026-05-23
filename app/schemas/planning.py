from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

ChecklistStatus = Literal["pending", "completed", "skipped", "failed"]
RuleCategory = Literal["rent", "bill", "gas", "saving", "investment", "custom"]
GoalType = Literal["save", "invest", "debt", "expense_control", "custom"]


class FinancialPlanCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    goal_type: GoalType = "custom"
    target_amount: float | None = Field(default=None, ge=0)
    monthly_budget: float | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=1000)


class FinancialPlanResponse(BaseModel):
    id: int
    user_id: str
    title: str
    goal_type: GoalType
    target_amount: float | None
    monthly_budget: float | None
    status: str
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RecurringRuleCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    category: RuleCategory = "custom"
    amount: float = Field(gt=0)
    day_of_month: int = Field(ge=1, le=31)
    plan_id: int | None = None
    start_date: date | None = None
    autopay_enabled: bool = False
    requires_approval: bool = True
    reminder_days_before: int = Field(default=1, ge=0, le=14)


class ScheduleFromTextRequest(BaseModel):
    text: str = Field(min_length=5, max_length=500)
    plan_id: int | None = None
    default_amount: float = Field(default=0.0, ge=0)
    autopay_enabled: bool = False
    requires_approval: bool = True


class ScheduleFromTextResponse(BaseModel):
    rule: RecurringRuleResponse
    extracted: dict


class RecurringRuleUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    category: RuleCategory | None = None
    amount: float | None = Field(default=None, gt=0)
    day_of_month: int | None = Field(default=None, ge=1, le=31)
    autopay_enabled: bool | None = None
    requires_approval: bool | None = None
    trusted_recurring: bool | None = None
    is_active: bool | None = None
    reminder_days_before: int | None = Field(default=None, ge=0, le=14)


class RecurringRuleResponse(BaseModel):
    id: int
    user_id: str
    plan_id: int | None
    title: str
    category: RuleCategory
    amount: float
    day_of_month: int
    start_date: date
    next_run_date: date
    autopay_enabled: bool
    requires_approval: bool
    trusted_recurring: bool
    is_active: bool
    reminder_days_before: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChecklistItemResponse(BaseModel):
    id: int
    user_id: str
    recurring_rule_id: int | None
    title: str
    due_date: date
    amount: float | None
    status: ChecklistStatus
    notes: str | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChecklistStatusUpdateRequest(BaseModel):
    status: ChecklistStatus


class SchedulerMaterializeRequest(BaseModel):
    until_days: int = Field(default=14, ge=1, le=90)
