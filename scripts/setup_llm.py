"""Store a DeepSeek key locally without displaying it or modifying database settings."""

import getpass
from pathlib import Path

from dotenv import set_key


def main() -> None:
    path = Path(__file__).resolve().parents[1] / ".env"
    key = getpass.getpass("DeepSeek API key (hidden; blank cancels): ").strip()
    if not key:
        print("Cancelled. Configuration unchanged.")
        return
    if any(character.isspace() for character in key):
        raise SystemExit("Key must not contain whitespace.")
    set_key(str(path), "OPSMIND_LLM_API_KEY", key)
    set_key(str(path), "OPSMIND_LLM_BASE_URL", "https://api.deepseek.com")
    set_key(str(path), "OPSMIND_LLM_MODEL", "deepseek-v4-pro")
    set_key(str(path), "OPSMIND_LLM_PROVIDER", "deepseek")
    print("DeepSeek configuration saved to ignored .env. Database settings preserved.")


if __name__ == "__main__":
    main()
