"""Run locally: administrator password is prompted, never printed or saved."""

import getpass
import secrets
from pathlib import Path

import pymysql
from dotenv import dotenv_values, set_key
from sqlalchemy.engine import URL


def main() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if dotenv_values(env_path).get("OPSMIND_DATABASE_URL"):
        raise SystemExit("Database URL already configured; keeping existing credentials unchanged.")
    print("Create/use empty opsmind_dev and opsmind_test databases on 127.0.0.1:3306.")
    username = input("MySQL administrator username [root]: ").strip() or "root"
    password = getpass.getpass("MySQL administrator password (hidden): ")
    try:
        connection = pymysql.connect(
            host="127.0.0.1", port=3306, user=username, password=password, autocommit=True
        )
    except pymysql.MySQLError:
        raise SystemExit("MySQL login failed. Check local username/password and service.") from None
    suffix = secrets.token_hex(3)
    configs = [
        ("OPSMIND_DATABASE_URL", "opsmind_dev", "app", "SELECT, INSERT, UPDATE"),
        ("OPSMIND_MIGRATION_DATABASE_URL", "opsmind_dev", "migrate", "ALL PRIVILEGES"),
        ("OPSMIND_TEST_DATABASE_URL", "opsmind_test", "test", "ALL PRIVILEGES"),
    ]
    try:
        with connection.cursor() as cursor:
            for database in ("opsmind_dev", "opsmind_test"):
                cursor.execute(
                    "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=%s",
                    (database,),
                )
                if cursor.fetchone()[0]:
                    raise SystemExit(
                        f"{database} contains tables; stopping without modifying existing data."
                    )
            for database in ("opsmind_dev", "opsmind_test"):
                cursor.execute(
                    f"CREATE DATABASE IF NOT EXISTS {database} "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            for key, database, purpose, privileges in configs:
                account = f"opsmind_{purpose}_{suffix}"
                account_password = secrets.token_urlsafe(32)
                cursor.execute(
                    "CREATE USER %s@'localhost' IDENTIFIED BY %s", (account, account_password)
                )
                cursor.execute(f"GRANT {privileges} ON {database}.* TO %s@'localhost'", (account,))
                url = URL.create(
                    "mysql+pymysql",
                    username=account,
                    password=account_password,
                    host="127.0.0.1",
                    port=3306,
                    database=database,
                    query={"charset": "utf8mb4"},
                )
                set_key(str(env_path), key, url.render_as_string(hide_password=False))
    except pymysql.MySQLError:
        raise SystemExit(
            "Database setup failed. No existing data was deleted. "
            "Check administrator privileges; a partial setup may remain."
        ) from None
    finally:
        connection.close()
    print("Local database accounts configured. Credentials saved only in ignored .env.")
    print("Administrator password was not saved. You can now run migrations.")


if __name__ == "__main__":
    main()
