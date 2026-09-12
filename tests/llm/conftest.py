import json

import pytest

from opsmind.core.config import Settings


@pytest.fixture
def llm_settings():
    return Settings(
        _env_file=None,
        database_url="",
        llm_api_key="test-key-not-real",
        llm_provider="deepseek",
        llm_model="deepseek-v4-pro",
        llm_base_url="https://api.deepseek.com",
        llm_max_retries=1,
        llm_timeout_seconds=1,
        llm_total_timeout_seconds=5,
    )


@pytest.fixture
def analysis_data():
    return {
        "summary": "设备开机报警，原因未确认。",
        "possible_causes": ["可能为供电异常，需进一步确认。"],
        "missing_information": ["具体报警码是什么？"],
        "suggested_actions": ["记录报警信息并联系维修人员。"],
        "needs_human_review": True,
    }


@pytest.fixture
def envelope(analysis_data):
    return {
        "model": "deepseek-v4-pro",
        "choices": [
            {
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": json.dumps(analysis_data)},
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 80, "total_tokens": 180},
    }
