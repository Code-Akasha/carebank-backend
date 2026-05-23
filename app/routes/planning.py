from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.checklist_item import ChecklistItem
from app.models.financial_plan import FinancialPlan
from app.models.recurring_rule import RecurringRule
from app.models.user import User
from app.schemas.planning import (
    ChecklistItemResponse,
    ChecklistStatusUpdateRequest,
    FinancialPlanCreate,
    FinancialPlanResponse,
    RecurringRuleCreate,
    RecurringRuleResponse,
    RecurringRuleUpdate,
    ScheduleFromTextRequest,
    ScheduleFromTextResponse,
    SchedulerMaterializeRequest,
)
from app.services.planning_service import (
    create_plan_for_user,
    create_recurring_rule_for_user,
    create_schedule_from_text_for_user,
    materialize_due_checklists_for_user,
    materialize_rule_once_for_user,
    update_checklist_status_for_user,
    update_recurring_rule_for_user,
)

router = APIRouter(prefix="/api/planning", tags=["planning"])


@router.post(
    "/plans", response_model=FinancialPlanResponse, status_code=status.HTTP_201_CREATED,
)
def create_plan(
    body: FinancialPlanCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    return create_plan_for_user(db, current_user=current_user, body=body)


@router.get("/plans", response_model=list[FinancialPlanResponse])
def list_plans(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    return (
        db.query(FinancialPlan)
        .filter(FinancialPlan.user_id == current_user.user_id)
        .order_by(FinancialPlan.created_at.desc())
        .all()
    )


@router.get("/forecast")
def get_financial_forecast(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    # Mocking AI forecast for the user
    return {
        "predicted_balance_30d": 45000,
        "predicted_balance_90d": 52000,
        "safe_to_save": 3500,
        "status": "healthy",
        "confidence": 0.88,
    }


@router.post(
    "/recurring-rules",
    response_model=RecurringRuleResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_recurring_rule(
    body: RecurringRuleCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    return create_recurring_rule_for_user(db, current_user=current_user, body=body)


@router.post(
    "/schedule-from-text",
    response_model=ScheduleFromTextResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_schedule_from_text(
    body: ScheduleFromTextRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    return create_schedule_from_text_for_user(db, current_user=current_user, body=body)


@router.get("/recurring-rules", response_model=list[RecurringRuleResponse])
def list_recurring_rules(
    current_user: Annotated[User, Depends(get_current_user)],
    include_inactive: bool = False,
    db: Session = Depends(get_db),
):
    query = db.query(RecurringRule).filter(
        RecurringRule.user_id == current_user.user_id,
    )
    if not include_inactive:
        query = query.filter(RecurringRule.is_active.is_(True))
    return query.order_by(RecurringRule.next_run_date.asc()).all()


@router.patch("/recurring-rules/{rule_id}", response_model=RecurringRuleResponse)
def update_recurring_rule(
    rule_id: int,
    body: RecurringRuleUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    return update_recurring_rule_for_user(
        db,
        rule_id=rule_id,
        current_user=current_user,
        body=body,
    )


@router.post(
    "/recurring-rules/{rule_id}/materialize",
    response_model=ChecklistItemResponse,
    status_code=status.HTTP_201_CREATED,
)
def materialize_rule_once(
    rule_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    return materialize_rule_once_for_user(
        db,
        rule_id=rule_id,
        current_user=current_user,
    )


@router.post("/scheduler/materialize-due")
def materialize_due_checklists(
    body: SchedulerMaterializeRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    return materialize_due_checklists_for_user(
        db,
        current_user=current_user,
        until_days=body.until_days,
    )


@router.get("/checklist", response_model=list[ChecklistItemResponse])
def list_checklist(
    current_user: Annotated[User, Depends(get_current_user)],
    status_filter: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(ChecklistItem).filter(
        ChecklistItem.user_id == current_user.user_id,
    )

    if status_filter:
        query = query.filter(ChecklistItem.status == status_filter)
    if from_date:
        query = query.filter(ChecklistItem.due_date >= from_date)
    if to_date:
        query = query.filter(ChecklistItem.due_date <= to_date)

    return query.order_by(ChecklistItem.due_date.asc(), ChecklistItem.id.asc()).all()


@router.patch("/checklist/{item_id}", response_model=ChecklistItemResponse)
def update_checklist_status(
    item_id: int,
    body: ChecklistStatusUpdateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    return update_checklist_status_for_user(
        db,
        item_id=item_id,
        current_user=current_user,
        body=body,
    )
