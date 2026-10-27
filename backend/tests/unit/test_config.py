"""验证应用配置读取环境变量别名。"""

import pytest

from app.core.config import Settings


@pytest.mark.parametrize(
    ("api_key_name", "base_url_name"),
    [
        ("TOKENHUB_API_KEY", "TOKENHUB_BASE_URL"),
        ("TENCENT_TOKENHUB_API_KEY", "TENCENT_TOKENHUB_BASE_URL"),
    ],
)
def test_settings_reads_tokenhub_environment_variable_aliases(
    monkeypatch: pytest.MonkeyPatch,
    api_key_name: str,
    base_url_name: str,
) -> None:
    env_names = (
        "TOKENHUB_API_KEY",
        "TENCENT_TOKENHUB_API_KEY",
        "TOKENHUB_BASE_URL",
        "TENCENT_TOKENHUB_BASE_URL",
    )
    for env_name in env_names:
        monkeypatch.delenv(env_name, raising=False)
    monkeypatch.setenv(api_key_name, "test-tokenhub-key")
    monkeypatch.setenv(base_url_name, "https://tokenhub.test")

    settings = Settings(_env_file=None)

    assert settings.tokenhub_api_key.get_secret_value() == "test-tokenhub-key"
    assert settings.tokenhub_base_url == "https://tokenhub.test"
    assert settings.tokenhub_configured
