"""auth login 多 model 输入与 add model 测试"""

from unittest.mock import MagicMock, patch

import pytest

from illusion.cli import _prompt_models_and_create_env


def _make_env_config(api_format="anthropic", base_url="https://api.anthropic.com", models=None):
    """构造模拟 EnvConfig 对象"""
    env = MagicMock()
    env.api_format = api_format
    env.base_url = base_url
    models = models or {}
    env.list_models.return_value = models
    base: dict = {"api_format": api_format, "base_url": base_url}
    for i, m in enumerate(models.values()):
        base[f"model_{i + 1}"] = m
    env.model_dump.return_value = base
    return env


def _make_manager(envs=None):
    """构造模拟 AuthManager"""
    manager = MagicMock()
    envs = envs or {}
    manager.list_envs.return_value = envs
    manager.settings = MagicMock()
    return manager


def test_multiple_models_new_env_no_existing():
    """无已有 env 时，循环输入多个 model 并创建 env_1"""
    manager = _make_manager(envs={})
    inputs = ["claude-sonnet-4-6", "y", "claude-opus-4", "n"]
    with patch("builtins.input", side_effect=inputs):
        result = _prompt_models_and_create_env(
            manager=manager,
            api_format="anthropic",
            format_choice="anthropic",
            endpoint="https://api.anthropic.com",
            auth_field="api_key",
            credential="sk-test",
        )
    assert result == "env_1"
    env_config = manager.settings.env_1
    assert isinstance(env_config, dict)
    assert env_config["model_1"] == "claude-sonnet-4-6"
    assert env_config["model_2"] == "claude-opus-4"
    assert manager.settings.model == "env_1.model_1"
    manager.save_settings.assert_called_once()


def test_multiple_models_new_env_with_existing():
    """已有 env_1 时，新建 env_2（auth login 始终新建，不询问选择）"""
    existing_env = _make_env_config(models={"model_1": "existing-model"})
    manager = _make_manager(envs={"env_1": existing_env})
    inputs = ["claude-sonnet-4-6", "y", "claude-opus-4", "n"]
    with patch("builtins.input", side_effect=inputs):
        result = _prompt_models_and_create_env(
            manager=manager,
            api_format="anthropic",
            format_choice="anthropic",
            endpoint="https://api.anthropic.com",
            auth_field="api_key",
            credential="sk-new",
        )
    assert result == "env_2"
    env_config = manager.settings.env_2
    assert isinstance(env_config, dict)
    assert env_config["model_1"] == "claude-sonnet-4-6"
    assert env_config["model_2"] == "claude-opus-4"
    assert manager.settings.model == "env_2.model_1"


def test_default_enter_exits_loop():
    """回车默认退出 model 循环"""
    manager = _make_manager(envs={})
    inputs = ["claude-sonnet-4-6", ""]
    with patch("builtins.input", side_effect=inputs):
        result = _prompt_models_and_create_env(
            manager=manager,
            api_format="anthropic",
            format_choice="anthropic",
            endpoint="https://api.anthropic.com",
            auth_field="api_key",
            credential="sk-test",
        )
    assert result == "env_1"
    env_config = manager.settings.env_1
    assert isinstance(env_config, dict)
    assert "model_1" in env_config
    assert "model_2" not in env_config


def test_credential_stored_for_new_env():
    """新建 env 时存储凭据"""
    manager = _make_manager(envs={})
    inputs = ["claude-sonnet-4-6", "n"]
    with (
        patch("builtins.input", side_effect=inputs),
        patch("illusion.auth.storage.store_env_credential") as mock_store,
    ):
        _prompt_models_and_create_env(
            manager=manager,
            api_format="anthropic",
            format_choice="anthropic",
            endpoint="https://api.anthropic.com",
            auth_field="api_key",
            credential="sk-test",
        )
    mock_store.assert_called_once_with("env_1", "api_key", "sk-test")


def test_credential_none_skips_storage():
    """credential 为 None 时跳过凭据存储（copilot/codex）"""
    manager = _make_manager(envs={})
    inputs = ["gpt-4o", "n"]
    with (
        patch("builtins.input", side_effect=inputs),
        patch("illusion.auth.storage.store_env_credential") as mock_store,
    ):
        _prompt_models_and_create_env(
            manager=manager,
            api_format="copilot",
            format_choice="copilot",
            endpoint="https://api.githubcopilot.com",
            auth_field="api_key",
            credential=None,
            extra_env_fields={"api_key": ""},
        )
    mock_store.assert_not_called()
    env_config = manager.settings.env_1
    assert env_config["api_key"] == ""


def test_default_model_used_when_empty():
    """有默认 model 时，空输入使用默认 model"""
    manager = _make_manager(envs={})
    inputs = ["", "n"]  # 空输入 → 使用默认 model
    with patch("builtins.input", side_effect=inputs):
        result = _prompt_models_and_create_env(
            manager=manager,
            api_format="anthropic",
            format_choice="anthropic",
            endpoint="https://api.anthropic.com",
            auth_field="api_key",
            credential="sk-test",
        )
    assert result == "env_1"
    env_config = manager.settings.env_1
    # anthropic 默认 model 来自 _DEFAULT_MODELS
    assert env_config["model_1"]  # 非空


# ---- add model 测试 ----


def test_add_model_to_existing_env_interactive():
    """add model 交互式选择 env 并添加多个 model"""
    from illusion.cli import add_model

    existing_env = _make_env_config(models={"model_1": "claude-sonnet-4-6"})
    manager = _make_manager(envs={"env_1": existing_env})

    inputs = ["claude-opus-4", "y", "claude-haiku", "n"]
    with (
        patch("builtins.input", side_effect=inputs),
        patch("illusion.auth.manager.AuthManager", return_value=manager),
        patch("illusion.cli._ensure_language"),
        patch("illusion.cli.typer.prompt", return_value="1") as mock_prompt,
    ):
        try:
            add_model(env_key=None)  # type: ignore
        except SystemExit:
            pass

    mock_prompt.assert_called_once()
    env_config = manager.settings.env_1
    assert env_config["model_1"] == "claude-sonnet-4-6"
    assert env_config["model_2"] == "claude-opus-4"
    assert env_config["model_3"] == "claude-haiku"
    manager.save_settings.assert_called_once()


def test_add_model_with_env_key_arg():
    """add model env_1 直接指定 env"""
    from illusion.cli import add_model

    existing_env = _make_env_config(models={"model_1": "existing-model"})
    manager = _make_manager(envs={"env_1": existing_env})

    inputs = ["new-model", "n"]
    with (
        patch("builtins.input", side_effect=inputs),
        patch("illusion.auth.manager.AuthManager", return_value=manager),
        patch("illusion.cli._ensure_language"),
    ):
        try:
            add_model(env_key="env_1")  # type: ignore
        except SystemExit:
            pass

    env_config = manager.settings.env_1
    assert env_config["model_1"] == "existing-model"
    assert env_config["model_2"] == "new-model"


def test_add_model_env_not_exist():
    """add model 指定不存在的 env 时报错"""
    import typer

    from illusion.cli import add_model

    manager = _make_manager(envs={})
    with (
        patch("illusion.auth.manager.AuthManager", return_value=manager),
        patch("illusion.cli._ensure_language"),
        pytest.raises(typer.Exit),
    ):
        add_model(env_key="env_999")  # type: ignore


def test_add_model_no_existing_env():
    """无已有 env 时报错"""
    import typer

    from illusion.cli import add_model

    manager = _make_manager(envs={})
    with (
        patch("illusion.auth.manager.AuthManager", return_value=manager),
        patch("illusion.cli._ensure_language"),
        pytest.raises(typer.Exit),
    ):
        add_model(env_key=None)  # type: ignore
