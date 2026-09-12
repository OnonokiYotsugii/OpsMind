"""Insert demo rows after alembic upgrade head."""

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from opsmind.core.config import Settings
from opsmind.db.seed import seed_demo
from opsmind.db.session import create_db_engine


def main() -> None:
    settings = Settings()
    if settings.environment != "development":
        raise SystemExit("Demo seed is only allowed in development.")
    engine = create_db_engine(settings.database_url.get_secret_value())
    try:
        with Session(engine) as session:
            print("Inserted rows:", seed_demo(session))
    except SQLAlchemyError:
        raise SystemExit("Seed failed. Check database settings and run migrations first.") from None
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
