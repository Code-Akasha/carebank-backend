from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import get_settings

settings = get_settings()
engine = create_engine(
    settings.get_database_url(),
    pool_pre_ping=True,       # detect stale connections
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
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
