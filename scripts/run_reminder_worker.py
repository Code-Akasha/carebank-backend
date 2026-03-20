from __future__ import annotations

import json

from app.core.database import SessionLocal, init_db
from app.services.reminder_worker import run_reminder_worker


def main() -> None:
    init_db()
    with SessionLocal() as db:
        result = run_reminder_worker(db)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
