#!/usr/bin/env python3
"""
Reminder Worker Daemon

A production-ready reminder worker that can run continuously or as a scheduled job.
Includes monitoring, error handling, and escalation capabilities.
"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.database import SessionLocal, init_db
from app.services.reminder_worker import run_reminder_worker


class ReminderDaemon:
    """Production reminder worker daemon with monitoring and graceful shutdown."""

    def __init__(
        self,
        *,
        interval: int = 3600,  # 1 hour default
        horizon_days: int = 3,
        enable_monitoring: bool = True,
        log_level: str = "INFO",
    ) -> None:
        self.interval = interval
        self.horizon_days = horizon_days
        self.enable_monitoring = enable_monitoring
        self.running = False
        self.last_run: datetime | None = None
        self.total_runs = 0
        self.errors = 0

        # Setup logging
        logging.basicConfig(
            level=getattr(logging, log_level.upper()),
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler("reminder_worker.log"),
            ],
        )
        self.logger = logging.getLogger("reminder_daemon")

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, signum: int, frame: Any) -> None:
        """Handle shutdown signals gracefully."""
        signal_name = signal.Signals(signum).name
        self.logger.info(
            "Received %s signal, initiating graceful shutdown...", signal_name
        )
        self.stop()

    def _run_worker_cycle(self, db: Session) -> dict[str, Any]:
        """Run a single reminder worker cycle with error handling."""
        try:
            self.logger.info("Starting reminder worker cycle...")
            result = run_reminder_worker(db, horizon_days=self.horizon_days)

            # Log summary
            self.logger.info(
                "Worker cycle completed: materialized=%d, notifications=%d, actions=%d",
                result.get("materialized_checklists", 0),
                result.get("notifications_created", 0),
                result.get("action_requests_created", 0),
            )

            return result

        except Exception as exc:
            self.logger.exception("Worker cycle failed: %s", exc)
            self.errors += 1
            return {
                "error": str(exc),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    def _write_status_file(self, status: dict[str, Any]) -> None:
        """Write status information for monitoring."""
        if not self.enable_monitoring:
            return

        status_file = Path("reminder_worker_status.json")
        try:
            with status_file.open("w") as f:
                json.dump(status, f, indent=2)
        except Exception as exc:
            self.logger.warning("Failed to write status file: %s", exc)

    def _escalate_overdue_items(self, db: Session) -> None:
        """Escalate severely overdue items (e.g., send high-priority notifications)."""
        try:
            from app.models.checklist_item import ChecklistItem
            from app.models.user import User
            from datetime import date, timedelta

            # Find items overdue by more than 7 days
            cutoff = date.today() - timedelta(days=7)

            overdue_items = (
                db.query(ChecklistItem)
                .join(User, ChecklistItem.user_id == User.user_id)
                .filter(
                    User.is_active.is_(True),
                    ChecklistItem.status == "pending",
                    ChecklistItem.due_date < cutoff,
                )
                .all()
            )

            if not overdue_items:
                return

            self.logger.warning("Found %d severely overdue items", len(overdue_items))

            # For now, just log the escalation - could be extended to send alerts
            for item in overdue_items:
                days_overdue = (date.today() - item.due_date).days
                self.logger.error(
                    "ESCALATION: %s overdue by %d days for user %s (amount: %s)",
                    item.title,
                    days_overdue,
                    item.user_id,
                    item.amount,
                )

        except Exception as exc:
            self.logger.exception("Escalation check failed: %s", exc)

    def run_once(self) -> dict[str, Any]:
        """Run the worker once and return results."""
        import os

        init_db()

        with SessionLocal() as db:
            result = self._run_worker_cycle(db)

            # Run escalation check
            self._escalate_overdue_items(db)

            # Update status
            self.last_run = datetime.now(timezone.utc)
            self.total_runs += 1

            status = {
                "last_run": self.last_run.isoformat(),
                "total_runs": self.total_runs,
                "errors": self.errors,
                "result": result,
                "daemon_pid": os.getpid(),
            }

            self._write_status_file(status)

            return result

    def start(self) -> None:
        """Start the daemon (run continuously)."""
        self.logger.info(
            "Starting reminder worker daemon (interval=%ds)", self.interval
        )
        self.running = True

        while self.running:
            try:
                self.run_once()

                if self.running:  # Check if we should continue
                    self.logger.debug("Sleeping for %d seconds...", self.interval)
                    time.sleep(self.interval)

            except KeyboardInterrupt:
                self.logger.info("Received keyboard interrupt, shutting down...")
                break
            except Exception as exc:
                self.logger.exception("Unexpected error in daemon loop: %s", exc)
                self.errors += 1

                # Sleep before retrying
                time.sleep(min(300, self.interval))  # Max 5 minutes

        self.logger.info("Reminder worker daemon stopped")

    def stop(self) -> None:
        """Stop the daemon gracefully."""
        self.running = False

    def status(self) -> dict[str, Any]:
        """Get current daemon status."""
        return {
            "running": self.running,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "total_runs": self.total_runs,
            "errors": self.errors,
            "interval": self.interval,
            "horizon_days": self.horizon_days,
        }


def main() -> None:
    """Main entry point."""

    parser = argparse.ArgumentParser(description="Reminder Worker Daemon")
    parser.add_argument(
        "--mode",
        choices=["once", "daemon", "status"],
        default="once",
        help="Run mode: once (single run), daemon (continuous), or status (show status)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=3600,
        help="Interval between runs in seconds (daemon mode only)",
    )
    parser.add_argument(
        "--horizon-days",
        type=int,
        default=3,
        help="How many days ahead to look for upcoming items",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level",
    )
    parser.add_argument(
        "--no-monitoring",
        action="store_true",
        help="Disable status file monitoring",
    )

    args = parser.parse_args()

    daemon = ReminderDaemon(
        interval=args.interval,
        horizon_days=args.horizon_days,
        enable_monitoring=not args.no_monitoring,
        log_level=args.log_level,
    )

    if args.mode == "once":
        result = daemon.run_once()
        print(json.dumps(result, indent=2))

    elif args.mode == "daemon":
        daemon.start()

    elif args.mode == "status":
        status = daemon.status()
        print(json.dumps(status, indent=2))

        # Also show status file if it exists
        status_file = Path("reminder_worker_status.json")
        if status_file.exists():
            print("\nLast status file:")
            with status_file.open("r") as f:
                print(f.read())


if __name__ == "__main__":
    main()
