"""Engine configuration with bounded timeouts and hidden SQL parameters."""

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import URL, make_url


def validated_mysql_url(raw: str) -> URL:
    if not raw:
        raise ValueError("Database URL is not configured.")
    try:
        url = make_url(raw)
    except Exception:
        raise ValueError("Database URL is invalid.") from None
    if url.drivername != "mysql+pymysql" or not url.database or not url.username:
        raise ValueError("A mysql+pymysql URL with username and database is required.")
    return url


def create_db_engine(raw: str) -> Engine:
    return create_engine(
        validated_mysql_url(raw),
        pool_pre_ping=True,
        pool_recycle=1800,
        hide_parameters=True,
        connect_args={"connect_timeout": 5, "read_timeout": 10, "write_timeout": 10},
    )
