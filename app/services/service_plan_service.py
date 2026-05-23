"""Service plan CRUD operations for business accounts."""

from __future__ import annotations

import logging

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.service_plan import ServicePlan
from app.models.user import User
from app.schemas.business import ServicePlanCreate, ServicePlanUpdate

logger = logging.getLogger(__name__)


def require_business_user(db: Session, user_id: str) -> User:
    """Verify the user exists and has a business account."""
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found",
        )
    if user.account_type != "business":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only business accounts can manage service plans",
        )
    return user


def create_service_plan(
    db: Session, user_id: str, payload: ServicePlanCreate,
) -> ServicePlan:
    """Create a new service plan for a business."""
    require_business_user(db, user_id)

    plan = ServicePlan(
        business_user_id=user_id,
        plan_name=payload.plan_name,
        unit_label=payload.unit_label,
        unit_price=payload.unit_price,
        currency=payload.currency,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    logger.info("Service plan %d created by %s: %s", plan.id, user_id, plan.plan_name)
    return plan


def list_service_plans(
    db: Session,
    business_user_id: str | None = None,
    active_only: bool = True,
) -> list[ServicePlan]:
    """List service plans, optionally filtered by business user."""
    query = db.query(ServicePlan)
    if business_user_id:
        query = query.filter(ServicePlan.business_user_id == business_user_id)
    if active_only:
        query = query.filter(ServicePlan.is_active == True)  # noqa: E712
    return query.order_by(ServicePlan.created_at.desc()).all()


def update_service_plan(
    db: Session, user_id: str, plan_id: int, payload: ServicePlanUpdate,
) -> ServicePlan:
    """Update an existing service plan owned by the user."""
    plan = db.query(ServicePlan).filter(ServicePlan.id == plan_id).first()
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Service plan not found",
        )
    if plan.business_user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not your plan",
        )

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(plan, field, value)

    db.commit()
    db.refresh(plan)
    return plan


def get_service_plan(db: Session, plan_id: int) -> ServicePlan:
    """Get a single service plan by ID."""
    plan = db.query(ServicePlan).filter(ServicePlan.id == plan_id).first()
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Service plan not found",
        )
    return plan
