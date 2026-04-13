"""Recurring payment scheduler service using APScheduler."""

import logging
from datetime import datetime, timezone
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.recurring_payment_rule import RecurringPaymentRule
from app.schemas.payments import ExecutePaymentPayload
from app.services.payment_execution_service import execute_generic_payment

logger = logging.getLogger(__name__)

# Global scheduler instance
_scheduler: Optional[BackgroundScheduler] = None


def get_scheduler() -> BackgroundScheduler:
    """Get or create the global scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler()
        if not _scheduler.running:
            _scheduler.start()
            logger.info("Recurring payment scheduler started")
    return _scheduler


def start_scheduler() -> None:
    """Start the background scheduler for recurring payments."""
    scheduler = get_scheduler()
    if not scheduler.running:
        scheduler.start()
        logger.info("Recurring payment scheduler started")

        # Schedule daily check for recurring payments
        scheduler.add_job(
            check_and_execute_recurring_payments,
            trigger="cron",
            hour=0,
            minute=0,
            id="recurring_payment_check",
            name="Check and execute recurring payments",
            replace_existing=True,
        )
        logger.info("Recurring payment jobs scheduled")


def stop_scheduler() -> None:
    """Stop the background scheduler."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown()
        _scheduler = None
        logger.info("Recurring payment scheduler stopped")


def check_and_execute_recurring_payments() -> None:
    """Check for recurring payments to execute and execute them.

    This function is called by the scheduler at regular intervals.
    It finds all active recurring payment rules with next_run_date <= now
    and executes them.
    """
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc).date()

        # Find all active rules that are due for execution
        due_rules = (
            db.query(RecurringPaymentRule)
            .filter(
                RecurringPaymentRule.status == "active",
                RecurringPaymentRule.next_run_date <= now,
            )
            .all()
        )

        logger.info(f"Found {len(due_rules)} recurring payments due for execution")

        for rule in due_rules:
            try:
                execute_recurring_payment(db, rule)
            except Exception as exc:
                logger.error(
                    f"Failed to execute recurring payment rule {rule.id}: {exc}",
                    exc_info=True,
                )

    except Exception:
        logger.error("Error checking recurring payments", exc_info=True)
    finally:
        db.close()


def execute_recurring_payment(db: Session, rule: RecurringPaymentRule) -> None:
    """Execute a single recurring payment rule.

    Args:
        db: Database session
        rule: RecurringPaymentRule to execute
    """
    from app.services.recurring_payment_service import calculate_next_run_date

    logger.info(f"Executing recurring payment rule {rule.id}: {rule.description}")

    try:
        # Check if rule is expired
        if rule.end_date and rule.end_date < datetime.now(timezone.utc).date():
            rule.status = "expired"
            db.commit()
            logger.info(f"Recurring rule {rule.id} expired, status updated")
            return

        # Check if requires_approval
        if rule.requires_approval:
            logger.info(
                f"Recurring rule {rule.id} requires approval, skipping auto-execution"
            )
            rule.updated_at = datetime.now(timezone.utc)
            db.commit()
            return

        # Build payment payload
        payload = ExecutePaymentPayload(
            beneficiary_id=rule.beneficiary_id,
            amount=rule.amount,
            description=rule.description,
            payment_method="upi",  # Default, should be configurable per rule
            mpin=None,  # MPIN not needed for auto-recurring with requires_approval=False
        )

        # Execute payment
        result = execute_generic_payment(
            db, rule.user_id, payload, recurring_rule_id=str(rule.id)
        )

        # Update recurring rule execution stats
        rule.total_executions += 1
        rule.last_executed_at = datetime.now(timezone.utc)
        rule.last_execution_status = result.status

        # Calculate next run date
        rule.next_run_date = calculate_next_run_date(
            rule.frequency,
            rule.day_of_month,
            rule.day_of_week,
            datetime.now(timezone.utc),
        )

        db.commit()

        logger.info(
            f"Recurring payment rule {rule.id} executed successfully. Next run: {rule.next_run_date}"
        )

    except Exception as exc:
        logger.error(
            f"Failed to execute recurring payment rule {rule.id}: {exc}", exc_info=True
        )
        rule.last_execution_status = "failed"
        rule.updated_at = datetime.now(timezone.utc)
        db.commit()
        raise


def schedule_manual_recurring_execution(rule_id: str, delay_seconds: int = 10) -> None:
    """Schedule a manual execution of a recurring payment.

    Useful for immediate retry or manual trigger.

    Args:
        rule_id: ID of recurring payment rule to execute
        delay_seconds: Seconds to delay before execution (default 10)
    """
    scheduler = get_scheduler()

    scheduler.add_job(
        _execute_rule_by_id,
        "date",
        run_date=datetime.now(timezone.utc).replace(microsecond=0)
        + __import__("datetime").timedelta(seconds=delay_seconds),
        args=[rule_id],
        id=f"manual_recurring_{rule_id}_{datetime.now(timezone.utc).timestamp()}",
    )

    logger.info(f"Scheduled manual execution for recurring rule {rule_id}")


def _execute_rule_by_id(rule_id: str) -> None:
    """Helper function to execute a recurring rule by ID."""
    db = SessionLocal()
    try:
        rule = (
            db.query(RecurringPaymentRule)
            .filter(RecurringPaymentRule.id == rule_id)
            .first()
        )
        if rule:
            execute_recurring_payment(db, rule)
        else:
            logger.warning(f"Recurring payment rule {rule_id} not found")
    except Exception as exc:
        logger.error(
            f"Failed to execute recurring rule {rule_id}: {exc}", exc_info=True
        )
    finally:
        db.close()


def pause_recurring_execution(rule_id: str) -> None:
    """Pause a recurring payment (remove from scheduler)."""
    scheduler = get_scheduler()
    job_id = f"recurring_rule_{rule_id}"

    try:
        scheduler.remove_job(job_id)
        logger.info(f"Removed recurring payment {rule_id} from scheduler")
    except Exception:
        # Job might not have been scheduled yet, that's fine
        pass


def resume_recurring_execution(rule_id: str) -> None:
    """Resume a paused recurring payment."""
    db = SessionLocal()
    try:
        rule = (
            db.query(RecurringPaymentRule)
            .filter(RecurringPaymentRule.id == rule_id)
            .first()
        )
        if rule and rule.status == "paused":
            # Schedule will pick it up on next check
            logger.info(f"Recurring payment {rule_id} marked for resume")
        else:
            logger.warning(
                f"Cannot resume recurring rule {rule_id}: not paused or not found"
            )
    finally:
        db.close()
