from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import get_settings

settings = get_settings()
database_url = settings.get_database_url()

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
    import app.models.user_profile  # noqa: F401
    import app.models.financial_plan  # noqa: F401
    import app.models.recurring_rule  # noqa: F401
    import app.models.checklist_item  # noqa: F401
    import app.models.notification  # noqa: F401
    import app.models.bill_snooze  # noqa: F401
    import app.models.action_request  # noqa: F401
    import app.models.action_execution  # noqa: F401
    import app.models.idempotency_record  # noqa: F401

    mode = (settings.db_schema_mode or "create_all").strip().lower()
    if mode in {"create_all", "dev"}:
        Base.metadata.create_all(bind=engine)
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


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
