from pathlib import Path
import logging
import time

from sqlalchemy import create_engine, inspect, text, event
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import NullPool

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
        pool_size=5,
        max_overflow=10,
        pool_recycle=3600,
        connect_args={"connect_timeout": 60, "options": "-c statement_timeout=30000"},
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

    # Admin LLM and tunnel configuration models
    import app.models.llm_tunnel_config  # noqa: F401
    import app.models.agent_prompt_config  # noqa: F401
    import app.models.admin_action_log  # noqa: F401
    import app.models.banking_connector_config  # noqa: F401

    # Test database connection first
    _test_database_connection()

    mode = (settings.db_schema_mode or "create_all").strip().lower()
    if mode in {"create_all", "dev"}:
        try:
            Base.metadata.create_all(bind=engine)
            _apply_dev_schema_backfills()
            logger.info("Database schema created/verified successfully")
        except Exception as e:
            logger.error(f"Database initialization failed: {e}", exc_info=True)
            raise
        return

    if mode in {"alembic", "migrate"}:
        _run_alembic_upgrade()
        return

    raise ValueError(f"Unsupported DB_SCHEMA_MODE={settings.db_schema_mode!r}")


def _test_database_connection(max_retries: int = 10) -> None:
    """Test database connection with exponential backoff retries."""
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
                logger.info("Database connection test successful")
                return
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                wait_time = min(2 ** (attempt - 1), 10)  # 1s, 2s, 4s, 8s, 10s, ...
                logger.warning(
                    f"Database connection attempt {attempt}/{max_retries} failed: {e}. "
                    f"Retrying in {wait_time}s..."
                )
                time.sleep(wait_time)
            else:
                logger.error(
                    f"Database connection failed after {max_retries} attempts: {e}",
                    exc_info=True,
                )
    raise RuntimeError(
        f"Cannot connect to database at {settings.get_database_url()} after {max_retries} "
        f"attempts: {last_error}"
    ) from last_error


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

    if "products" in tables:
        product_columns = {
            column["name"]: column for column in inspector.get_columns("products")
        }
        product_id_column = product_columns.get("id")
        if product_id_column is not None and str(
            product_id_column["type"]
        ).lower().startswith("integer"):
            logger.warning(
                "DB backfill: converting products.id from integer to varchar for provider compatibility"
            )
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE products ALTER COLUMN id TYPE VARCHAR USING id::text"
                    )
                )

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
