"""Bill creation, payment, and lifecycle management."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.bill import Bill
from app.models.business_profile import BusinessProfile
from app.models.service_plan import ServicePlan
from app.models.user import User
from app.schemas.business import BillCreate
from app.services.mpin_service import verify_mpin

logger = logging.getLogger(__name__)


def create_bill(db: Session, business_user_id: str, payload: BillCreate) -> dict:
    """Business issues a bill to a target user."""
    # Verify business account
    biz_user = db.query(User).filter(User.user_id == business_user_id).first()
    if not biz_user or biz_user.account_type != "business":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only business accounts can issue bills",
        )

    # Verify target user exists
    target = db.query(User).filter(User.user_id == payload.target_user_id).first()
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target user not found",
        )

    # Resolve plan name and amount
    plan_name = payload.plan_name or ""
    amount = payload.amount or 0.0

    if payload.service_plan_id:
        plan = (
            db.query(ServicePlan)
            .filter(
                ServicePlan.id == payload.service_plan_id,
                ServicePlan.business_user_id == business_user_id,
            )
            .first()
        )
        if not plan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Service plan not found or not owned by you",
            )
        if not plan.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Service plan is inactive",
            )
        plan_name = plan.plan_name
        if not payload.amount:
            amount = round(plan.unit_price * payload.quantity, 2)

    if amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Amount must be greater than zero",
        )
    if not plan_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="plan_name is required when service_plan_id is not provided",
        )

    bill = Bill(
        business_user_id=business_user_id,
        target_user_id=payload.target_user_id,
        service_plan_id=payload.service_plan_id,
        plan_name=plan_name,
        quantity=payload.quantity,
        amount=amount,
        description=payload.description,
        due_date=payload.due_date,
        status="pending",
    )
    db.add(bill)
    db.commit()
    db.refresh(bill)

    logger.info(
        "Bill %d issued: %s -> %s for ₹%.2f",
        bill.id,
        business_user_id,
        payload.target_user_id,
        amount,
    )

    # Enrich with business name for response
    biz_profile = (
        db.query(BusinessProfile)
        .filter(BusinessProfile.user_id == business_user_id)
        .first()
    )
    return _bill_to_dict(bill, biz_profile)


def list_bills_issued(
    db: Session,
    business_user_id: str,
    status_filter: str | None = None,
) -> list[dict]:
    """List bills issued by a business."""
    query = db.query(Bill).filter(Bill.business_user_id == business_user_id)
    if status_filter:
        query = query.filter(Bill.status == status_filter)
    bills = query.order_by(Bill.created_at.desc()).all()

    biz_profile = (
        db.query(BusinessProfile)
        .filter(BusinessProfile.user_id == business_user_id)
        .first()
    )
    return [_bill_to_dict(b, biz_profile) for b in bills]


def list_bills_received(
    db: Session,
    user_id: str,
    status_filter: str | None = None,
) -> list[dict]:
    """List bills received by a user."""
    query = db.query(Bill).filter(Bill.target_user_id == user_id)
    if status_filter:
        query = query.filter(Bill.status == status_filter)
    bills = query.order_by(Bill.created_at.desc()).all()

    result = []
    for bill in bills:
        biz_profile = (
            db.query(BusinessProfile)
            .filter(BusinessProfile.user_id == bill.business_user_id)
            .first()
        )
        result.append(_bill_to_dict(bill, biz_profile))
    return result


def pay_bill(
    db: Session,
    user_id: str,
    bill_id: int,
    mpin: str,
    payment_method: str = "upi",
) -> dict:
    """User pays a pending bill."""
    bill = db.query(Bill).filter(Bill.id == bill_id).first()
    if not bill:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bill not found",
        )
    if bill.target_user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This bill is not addressed to you",
        )
    if bill.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Bill is already {bill.status}",
        )

    # Verify MPIN
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    mpin_result = verify_mpin(db=db, current_user=user, mpin=mpin)
    if not mpin_result.get("verified"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=mpin_result.get("message", "MPIN verification failed"),
        )

    # Execute payment via banking client
    transaction_id = None
    try:
        from app.services.banking_client import get_banking_client

        client = get_banking_client()
        import asyncio

        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                txn_result = pool.submit(
                    asyncio.run,
                    client.trigger_transaction(
                        user_id=user_id,
                        amount=bill.amount,
                        merchant=bill.plan_name,
                        category="bill_payment",
                        description=bill.description
                        or f"Bill payment: {bill.plan_name}",
                        payment_rail=payment_method.upper(),
                    ),
                ).result()
        else:
            txn_result = asyncio.run(
                client.trigger_transaction(
                    user_id=user_id,
                    amount=bill.amount,
                    merchant=bill.plan_name,
                    category="bill_payment",
                    description=bill.description or f"Bill payment: {bill.plan_name}",
                    payment_rail=payment_method.upper(),
                ),
            )
        transaction_id = str(txn_result.get("transaction", {}).get("id", ""))
    except Exception as exc:
        logger.error("Bill payment proxy call failed for bill %d: %s", bill_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Payment processing failed",
        ) from exc

    # Update bill status
    bill.status = "paid"
    bill.paid_at = datetime.now(timezone.utc)
    bill.payment_transaction_id = transaction_id
    db.commit()
    db.refresh(bill)

    biz_profile = (
        db.query(BusinessProfile)
        .filter(BusinessProfile.user_id == bill.business_user_id)
        .first()
    )

    logger.info("Bill %d paid by %s, txn=%s", bill_id, user_id, transaction_id)
    return _bill_to_dict(bill, biz_profile)


def cancel_bill(db: Session, business_user_id: str, bill_id: int) -> dict:
    """Business cancels a pending bill."""
    bill = db.query(Bill).filter(Bill.id == bill_id).first()
    if not bill:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bill not found",
        )
    if bill.business_user_id != business_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not your bill",
        )
    if bill.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel a bill with status '{bill.status}'",
        )

    bill.status = "cancelled"
    db.commit()
    db.refresh(bill)

    biz_profile = (
        db.query(BusinessProfile)
        .filter(BusinessProfile.user_id == business_user_id)
        .first()
    )
    return _bill_to_dict(bill, biz_profile)


def _bill_to_dict(bill: Bill, biz_profile: BusinessProfile | None = None) -> dict:
    """Convert a Bill ORM object to a response dict."""
    return {
        "id": bill.id,
        "business_user_id": bill.business_user_id,
        "business_name": biz_profile.business_name if biz_profile else None,
        "target_user_id": bill.target_user_id,
        "service_plan_id": bill.service_plan_id,
        "plan_name": bill.plan_name,
        "quantity": bill.quantity,
        "amount": bill.amount,
        "currency": bill.currency,
        "description": bill.description,
        "status": bill.status,
        "due_date": bill.due_date,
        "paid_at": bill.paid_at,
        "payment_transaction_id": bill.payment_transaction_id,
        "created_at": bill.created_at,
    }
