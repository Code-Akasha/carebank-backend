"""Service plans routes — CRUD for business pricing plans."""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.business import (
    ServicePlanCreate,
    ServicePlanResponse,
    ServicePlanUpdate,
)
from app.services.service_plan_service import (
    create_service_plan,
    list_service_plans,
    update_service_plan,
)

router = APIRouter(prefix="/api/service-plans", tags=["service-plans"])


@router.post("", response_model=ServicePlanResponse, status_code=201)
def create_plan(
    body: ServicePlanCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    """Business creates a new service plan."""
    plan = create_service_plan(db, current_user.user_id, body)
    return plan


@router.get("", response_model=list[ServicePlanResponse])
def list_plans(
    current_user: Annotated[User, Depends(get_current_user)],
    business_user_id: Optional[str] = Query(
        None, description="Filter by business user ID"
    ),
    active_only: bool = Query(True),
    db: Session = Depends(get_db),
):
    """List service plans. Business sees own plans; users can filter by business."""
    filter_id = business_user_id
    if not filter_id and current_user.account_type == "business":
        filter_id = current_user.user_id
    return list_service_plans(db, business_user_id=filter_id, active_only=active_only)


@router.put("/{plan_id}", response_model=ServicePlanResponse)
def update_plan(
    plan_id: int,
    body: ServicePlanUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    """Business updates their service plan."""
    return update_service_plan(db, current_user.user_id, plan_id, body)
