"""Payment execution API routes."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.payments import ExecutePaymentPayload, PaymentExecutionResult
from app.services.payment_execution_service import execute_generic_payment

router = APIRouter(prefix="/api/payments", tags=["payments"])


@router.post("/execute", response_model=PaymentExecutionResult)
async def execute_payment(
    payload: ExecutePaymentPayload,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Execute a one-time payment to a beneficiary.

    Flow:
    1. Validate payment method available (phone for UPI, account for transfer)
    2. Validate amount against per-transaction and daily limits
    3. Check if MPIN is required (first payment or amount > threshold)
    4. Verify MPIN if required
    5. Execute payment via MockBank
    6. Return result with transaction ID

    Required fields:
    - beneficiary_id: ID of saved beneficiary
    - amount: Payment amount in rupees
    - payment_method: "upi" or "account_transfer"
    - description: (Optional) Payment description/reason

    Conditional fields:
    - mpin: Required if payment requires MPIN (first payment or amount > threshold)
    """
    return execute_generic_payment(db, current_user.user_id, payload)
