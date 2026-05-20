from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

from app.core.config import get_settings
from app.core.database import Base

# Import all models so Alembic autogenerate sees every table.
import app.models.balance  # noqa: F401
import app.models.transaction  # noqa: F401
import app.models.product  # noqa: F401
import app.models.account  # noqa: F401
import app.models.provider  # noqa: F401
import app.models.session  # noqa: F401
import app.models.audit_log  # noqa: F401
import app.models.user  # noqa: F401
import app.models.user_profile  # noqa: F401
import app.models.user_mpin  # noqa: F401
import app.models.financial_plan  # noqa: F401
import app.models.recurring_rule  # noqa: F401
import app.models.checklist_item  # noqa: F401
import app.models.notification  # noqa: F401
import app.models.bill_snooze  # noqa: F401
import app.models.action_request  # noqa: F401
import app.models.action_execution  # noqa: F401
import app.models.idempotency_record  # noqa: F401

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Override sqlalchemy.url from app settings (env-based)
# Set the SQLAlchemy URL from runtime settings.
# Escape '%' characters so ConfigParser in Alembic does not attempt interpolation
# when URLs contain percent-encoded characters (e.g. passwords with special chars).
url = get_settings().get_database_url()
config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Models metadata for autogenerate
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
