"""One-shot schema migration and demo seed, using the dedicated migration account."""

from alembic.config import Config
from sqlalchemy.orm import Session

from alembic import command
from opsmind.core.config import Settings
from opsmind.db.seed import seed_demo
from opsmind.db.session import create_db_engine, validated_mysql_url


def main() -> None:
    settings = Settings()
    raw = settings.migration_database_url.get_secret_value()
    url = validated_mysql_url(raw)
    if settings.environment != "development" or url.host != "db" or url.database != "opsmind_demo":
        raise SystemExit("Container initialization requires the isolated demo database.")
    config = Config("alembic.ini")
    config.attributes["database_url"] = raw
    command.upgrade(config, "head")
    engine = create_db_engine(raw)
    try:
        with Session(engine) as session:
            counts = seed_demo(session)
        print("Container demo rows inserted:", counts)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
