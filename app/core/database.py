from pathlib import Path
import logging

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import get_settings

settings = get_settings()
database_url = settings.get_database_url()
logger = logging.getLogger(__name__)

if database_url.startswith("sqlite"):
    engine = create_engine(
        database_url,
        pool_pre_ping=True,
    )
else:
    engine = create_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def init_db() -> None:
    """Import all models so their tables are registered, then create any missing ones."""
    import app.models.balance  # noqa: F401
    import app.models.transaction  # noqa: F401
    import app.models.product  # noqa: F401
    import app.models.account  # noqa: F401
    import app.models.provider  # noqa: F401
    import app.models.session  # noqa: F401
    import app.models.audit_log  # noqa: F401
    import app.models.user  # noqa: F401
    import app.models.user_mpin  # noqa: F401
    import app.models.user_profile  # noqa: F401
    import app.models.financial_plan  # noqa: F401
    import app.models.recurring_rule  # noqa: F401
    import app.models.checklist_item  # noqa: F401
    import app.models.notification  # noqa: F401
    import app.models.bill_snooze  # noqa: F401
    import app.models.action_request  # noqa: F401
    import app.models.action_execution  # noqa: F401
    import app.models.idempotency_record  # noqa: F401
    
    # Payment system models (generic payments + recurring bills)
    import app.models.payment_settings  # noqa: F401
    import app.models.beneficiary  # noqa: F401
    import app.models.recurring_payment_rule  # noqa: F401
    import app.models.payment_history  # noqa: F401

    mode = (settings.db_schema_mode or "create_all").strip().lower()
    if mode in {"create_all", "dev"}:
        Base.metadata.create_all(bind=engine)
        _apply_dev_schema_backfills()
        return

    if mode in {"alembic", "migrate"}:
        _run_alembic_upgrade()
        return

    raise ValueError(f"Unsupported DB_SCHEMA_MODE={settings.db_schema_mode!r}")


def _run_alembic_upgrade() -> None:
    from alembic import command
    from alembic.config import Config

    repo_root = Path(__file__).resolve().parents[2]
    alembic_ini = repo_root / "alembic.ini"
    if not alembic_ini.exists():
        raise FileNotFoundError(f"alembic.ini not found at {alembic_ini}")

    config = Config(str(alembic_ini))
    command.upgrade(config, "head")


def _apply_dev_schema_backfills() -> None:
    """Apply additive schema fixes that create_all cannot perform on existing tables."""
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "users" not in tables:
        return

    user_columns = {column["name"] for column in inspector.get_columns("users")}
    if "telegram_user_id" in user_columns:
        return

    logger.warning(
        "DB backfill: adding missing users.telegram_user_id column for schema compatibility"
    )
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE users ADD COLUMN telegram_user_id VARCHAR"))
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_telegram_user_id ON users (telegram_user_id)"
            )
        )


async def get_db():
    """Database session dependency - automatically manages connection lifecycle."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
