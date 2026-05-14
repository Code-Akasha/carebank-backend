"""Payment execution service for processing one-time and recurring payments."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.models.beneficiary import Beneficiary
from app.models.payment_history import PaymentHistory
from app.models.user import User
from app.schemas.payments import ExecutePaymentPayload, PaymentExecutionResult
from app.services.beneficiary_service import record_payment_to_beneficiary
from app.services.payment_settings_service import (
    check_daily_limit,
    get_or_create_payment_settings,
    verify_mpin,
)


# Payment limits by verification status
PAYMENT_LIMITS = {
    "upi_verified": 200000.0,  # ₹2 lakh
    "upi_unverified": 50000.0,  # ₹50k
    "account_transfer_verified": 500000.0,  # ₹5 lakh
    "account_transfer_unverified": 100000.0,  # ₹1 lakh
}


def validate_payment_method_available(
    db: Session, user_id: str, payment_method: str
) -> tuple[bool, str | None]:
    """Check if payment method is available for user.

    Returns: (is_available, error_message)
    """
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if payment_method == "upi":
        if not user.phone_number:
            return (
                False,
                "UPI payment requires phone number. Please add phone number in onboarding settings.",
            )
        return True, None
    elif payment_method == "account_transfer":
        if not user.account_number or not user.account_ifsc:
            return (
                False,
                "Account transfer requires account number and IFSC. Please add account details in onboarding settings.",
            )
        return True, None
    else:
        return False, f"Unsupported payment method: {payment_method}"


def get_per_transaction_limit(payment_method: str, is_verified: bool) -> float:
    """Get per-transaction limit based on method and verification status."""
    if payment_method == "upi":
        return PAYMENT_LIMITS["upi_verified" if is_verified else "upi_unverified"]
    elif payment_method == "account_transfer":
        return PAYMENT_LIMITS[
            "account_transfer_verified"
            if is_verified
            else "account_transfer_unverified"
        ]
    else:
        raise ValueError(f"Unknown payment method: {payment_method}")


def validate_payment_amount(
    db: Session,
    user_id: str,
    beneficiary_id: str,
    payment_amount: float,
    payment_method: str,
) -> tuple[bool, str | None]:
    """Validate payment amount against limits.

    Returns: (is_valid, error_message)
    """
    if payment_amount <= 0:
        return False, "Payment amount must be positive"

    # Get beneficiary to check verification status
    beneficiary = (
        db.query(Beneficiary)
        .filter(
            Beneficiary.id == beneficiary_id,
            Beneficiary.user_id == user_id,
        )
        .first()
    )

    if not beneficiary:
        return False, "Beneficiary not found"

    # Check per-transaction limit
    limit = get_per_transaction_limit(payment_method, beneficiary.is_verified)
    if payment_amount > limit:
        return (
            False,
            f"Amount exceeds {payment_method} limit of ₹{limit} ({get_limit_name(beneficiary.is_verified)})",
        )

    # Check daily limit
    is_within_daily, daily_error = check_daily_limit(db, user_id, payment_amount)
    if not is_within_daily:
        return False, daily_error

    return True, None


def should_require_mpin(
    db: Session,
    user_id: str,
    payment_amount: float,
    is_first_payment_to_beneficiary: bool,
    beneficiary_is_trusted: bool = False,
) -> bool:
    """Determine if MPIN is required for this payment.

    Rules:
    1. First payment to any beneficiary always requires MPIN
    2. Subsequent payments require MPIN if amount > threshold
    3. Trusted beneficiaries can auto-execute within threshold if auto_approve_trusted=True
    """
    settings = get_or_create_payment_settings(db, user_id)

    # Trusted beneficiaries can auto-execute within threshold.
    if beneficiary_is_trusted and settings.auto_approve_trusted and payment_amount <= settings.mpin_threshold:
        return False

    # First payment requires MPIN only if it is not trusted/auto-approved.
    if is_first_payment_to_beneficiary:
        return True

    if payment_amount > settings.mpin_threshold:
        return True

    return False


def execute_generic_payment(
    db: Session,
    user_id: str,
    payload: ExecutePaymentPayload,
    recurring_rule_id: int | None = None,
) -> PaymentExecutionResult:
    """Execute a payment (one-time or recurring).

    Flow:
    1. Validate payment method is available
    2. Get beneficiary and validate amount
    3. Check if MPIN is required
    4. Verify MPIN if required
    5. Call MockBank to execute transaction
    6. Record payment history
    7. Update beneficiary stats
    8. Return result
    """
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Step 1: Validate payment method available
    is_available, method_error = validate_payment_method_available(
        db, user_id, payload.payment_method
    )
    if not is_available:
        raise HTTPException(status_code=400, detail=method_error)

    # Step 2: Get beneficiary and validate amount
    beneficiary = (
        db.query(Beneficiary)
        .filter(
            Beneficiary.id == payload.beneficiary_id,
            Beneficiary.user_id == user_id,
        )
        .first()
    )

    if not beneficiary:
        raise HTTPException(status_code=404, detail="Beneficiary not found")

    is_valid, amount_error = validate_payment_amount(
        db,
        user_id,
        payload.beneficiary_id,
        payload.amount,
        payload.payment_method,
    )

    if not is_valid:
        raise HTTPException(status_code=400, detail=amount_error)

    # Step 3: Check if MPIN is required
    is_first_payment = beneficiary.payment_count == 0
    requires_mpin = should_require_mpin(
        db,
        user_id,
        payload.amount,
        is_first_payment,
        beneficiary_is_trusted=bool(beneficiary.is_trusted),
    )

    # Step 4: Verify MPIN if required
    if requires_mpin:
        if not payload.mpin:
            raise HTTPException(
                status_code=400, detail="MPIN required for this payment"
            )

        try:
            if not verify_mpin(db, user_id, payload.mpin):
                raise HTTPException(status_code=401, detail="MPIN incorrect")
        except HTTPException as e:
            if "not configured" in str(e.detail):
                raise HTTPException(
                    status_code=400,
                    detail="Payment requires MPIN but MPIN not configured. Please set MPIN in settings.",
                )
            raise

    # Step 5: Call MockBank to execute transaction
    idempotency_key = str(uuid4())
    error_reason = None
    try:
        # TODO: Call MockBank integration here
        # For now, assume transaction succeeds
        mockbank_transaction_id = f"MB-{uuid4().hex[:16].upper()}"
        transaction_status = "success"
    except Exception as e:
        transaction_status = "failed"
        error_reason = str(e)
        mockbank_transaction_id = None

    # Step 6: Record payment history
    payment_record = PaymentHistory(
        user_id=user_id,
        beneficiary_id=payload.beneficiary_id,
        recurring_rule_id=recurring_rule_id,
        payment_type="recurring" if recurring_rule_id else "once",
        payment_method=payload.payment_method,
        amount=payload.amount,
        description=payload.description,
        status=transaction_status,
        mockbank_transaction_id=mockbank_transaction_id,
        error_reason=error_reason if transaction_status == "failed" else None,
        idempotency_key=idempotency_key,
        execution_date=datetime.now(timezone.utc),
    )
    db.add(payment_record)
    db.commit()
    db.refresh(payment_record)

    # Step 7: Update beneficiary stats if successful
    if transaction_status == "success":
        record_payment_to_beneficiary(db, payload.beneficiary_id, user_id=user_id)

    # Step 8: Return result
    beneficiary_label = beneficiary.nickname or beneficiary.identifier_value
    if transaction_status == "success":
        return PaymentExecutionResult(
            status="success",
            message=f"Payment of ₹{payload.amount} to {beneficiary_label} successful",
            execution_id=payment_record.id,
            transaction_id=mockbank_transaction_id,
        )
    else:
        return PaymentExecutionResult(
            status="failed",
            message=f"Payment failed: {error_reason}",
            execution_id=payment_record.id,
            error_reason=error_reason,
        )


def get_limit_name(is_verified: bool) -> str:
    """Get friendly name for verification status."""
    return "verified" if is_verified else "unverified"
