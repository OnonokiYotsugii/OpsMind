"""Generate ignored, independent container credentials; never overwrite local .env."""

import secrets
from pathlib import Path

from opsmind.core.config import Settings


def generate(target: Path, settings: Settings) -> None:
    # Fail closed rather than silently changing credentials for an existing volume.
    app_password = secrets.token_hex(24)
    migration_password = secrets.token_hex(24)
    sql = (
        f"CREATE USER 'opsmind_app'@'%' IDENTIFIED BY '{app_password}';\n"
        f"CREATE USER 'opsmind_migrate'@'%' IDENTIFIED BY '{migration_password}';\n"
        "GRANT SELECT, INSERT, UPDATE ON opsmind_demo.* TO 'opsmind_app'@'%';\n"
        "GRANT ALL PRIVILEGES ON opsmind_demo.* TO 'opsmind_migrate'@'%';\n"
    )
    base = "OPSMIND_ENVIRONMENT=development\n"
    app_url = f"mysql+pymysql://opsmind_app:{app_password}@db:3306/opsmind_demo?charset=utf8mb4"
    migration_url = (
        f"mysql+pymysql://opsmind_migrate:{migration_password}@db:3306/opsmind_demo?charset=utf8mb4"
    )
    # Single-quoted dotenv values are literal; reject line breaks and quotes.
    values = {
        "OPSMIND_DATABASE_URL": app_url,
        "OPSMIND_LLM_PROVIDER": settings.llm_provider,
        "OPSMIND_LLM_BASE_URL": settings.llm_base_url,
        "OPSMIND_LLM_MODEL": settings.llm_model,
        "OPSMIND_LLM_API_KEY": settings.llm_api_key.get_secret_value(),
    }
    if any(any(c in v for c in "\r\n'") for v in values.values()):
        raise ValueError("Container configuration contains unsupported characters.")
    target.mkdir(parents=True, exist_ok=False)
    (target / "root-password").write_text(secrets.token_hex(32), encoding="utf-8")
    (target / "init.sql").write_text(sql, encoding="utf-8")
    (target / "migration.env").write_text(
        base + f"OPSMIND_MIGRATION_DATABASE_URL={migration_url}\n", encoding="utf-8"
    )
    (target / "app.env").write_text(
        base + "".join(f"{key}='{value}'\n" for key, value in values.items()), encoding="utf-8"
    )


def main() -> None:
    target = Path(__file__).resolve().parents[1] / ".data" / "docker"
    try:
        generate(target, Settings())
    except FileExistsError:
        raise SystemExit("Container settings already exist; kept unchanged.") from None
    print("Container settings saved under ignored .data/docker. Local .env unchanged.")


if __name__ == "__main__":
    main()
