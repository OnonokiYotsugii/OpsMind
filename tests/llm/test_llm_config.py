import pytest
from pydantic import ValidationError

from opsmind.core.config import Settings


@pytest.mark.parametrize(
    "url",
    [
        "http://api.deepseek.com",
        "https://name:password@example.com",
        "https://example.com?key=secret",
        "https://example.com#fragment",
        "not-a-url",
    ],
)
def test_reject_unsafe_base_url(url):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, llm_base_url=url)


@pytest.mark.parametrize(
    "values",
    [
        {"llm_max_retries": -1},
        {"llm_max_retries": 4},
        {"llm_timeout_seconds": 0},
        {"llm_total_timeout_seconds": 0},
        {"llm_max_output_tokens": 1000000},
    ],
)
def test_call_budget_settings_are_bounded(values):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)


def test_key_masked_in_settings():
    settings = Settings(_env_file=None, llm_api_key="private-key-example")
    assert "private-key-example" not in repr(settings)
    assert "private-key-example" not in settings.model_dump_json()
