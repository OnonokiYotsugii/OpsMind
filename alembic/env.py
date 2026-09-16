"""Read migration credentials from Settings, never from a committed ini file."""

from alembic import context
from opsmind.agent.models import AgentRun  # noqa: F401
from opsmind.core.config import Settings
from opsmind.db.models import Base
from opsmind.db.session import create_db_engine, validated_mysql_url
from opsmind.rag.models import KnowledgeDocument  # noqa: F401

config = context.config
target_metadata = Base.metadata


def database_url() -> str:
    override = config.attributes.get("database_url")
    if override:
        return override
    settings = Settings()
    raw = settings.migration_database_url.get_secret_value()
    if not raw:
        raise ValueError("Set OPSMIND_MIGRATION_DATABASE_URL before running migrations.")
    return raw


if context.is_offline_mode():
    context.configure(
        url=validated_mysql_url(database_url()),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_db_engine(database_url())
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()
