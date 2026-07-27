"""auth login 多 model 输入与 env 复用测试"""

from unittest.mock import MagicMock, patch

import pytest

from illusion.cli import _prompt_models_and_env


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


def test_multiple_models_new_env():
    """无 --env 且无已有 env 时，循环输入多个 model 并创建新 env"""
    manager = _make_manager(envs={})
    inputs = ["claude-sonnet-4-6", "y", "claude-opus-4", "n"]
    with patch("builtins.input", side_effect=inputs):
        result = _prompt_models_and_env(
            manager=manager,
            api_format="anthropic",
            format_choice="anthropic",
            endpoint="https://api.anthropic.com",
            auth_field="api_key",
            credential="sk-test",
            env_key_arg=None,
        )
    assert result == "env_1"
    # setattr(manager.settings, "env_1", env_config) 将 dict 存到 manager.settings.env_1
    env_config = manager.settings.env_1
    assert isinstance(env_config, dict)
    assert env_config["model_1"] == "claude-sonnet-4-6"
    assert env_config["model_2"] == "claude-opus-4"
    # 新建 env 时设置 active model
    assert manager.settings.model == "env_1.model_1"
    manager.save_settings.assert_called_once()


def test_multiple_models_with_env_arg():
    """--env 参数追加多个 model 到已有 env"""
    existing_env = _make_env_config(models={"model_1": "claude-sonnet-4-6"})
    manager = _make_manager(envs={"env_1": existing_env})
    inputs = ["claude-opus-4", "y", "claude-haiku", "n"]
    with patch("builtins.input", side_effect=inputs):
        result = _prompt_models_and_env(
            manager=manager,
            api_format="anthropic",
            format_choice="anthropic",
            endpoint="https://api.anthropic.com",
            auth_field="api_key",
            credential="sk-new",
            env_key_arg="env_1",
        )
    assert result == "env_1"
    # 验证追加后 env_config 包含 model_1, model_2, model_3
    env_config = manager.settings.env_1
    assert isinstance(env_config, dict)
    assert env_config["model_1"] == "claude-sonnet-4-6"
    assert env_config["model_2"] == "claude-opus-4"
    assert env_config["model_3"] == "claude-haiku"


def test_default_enter_exits_loop():
    """回车默认退出 model 循环"""
    manager = _make_manager(envs={})
    inputs = ["claude-sonnet-4-6", ""]  # 回车 = 不继续
    with patch("builtins.input", side_effect=inputs):
        result = _prompt_models_and_env(
            manager=manager,
            api_format="anthropic",
            format_choice="anthropic",
            endpoint="https://api.anthropic.com",
            auth_field="api_key",
            credential="sk-test",
            env_key_arg=None,
        )
    assert result == "env_1"
    env_config = manager.settings.env_1
    assert isinstance(env_config, dict)
    assert "model_1" in env_config
    assert "model_2" not in env_config  # 只添加了一个


def test_env_arg_not_exist():
    """--env 指定不存在的 env 时报错退出"""
    manager = _make_manager(envs={})
    inputs = ["claude-sonnet-4-6", "n"]
    import typer

    with patch("builtins.input", side_effect=inputs), pytest.raises(typer.Exit):
        _prompt_models_and_env(
            manager=manager,
            api_format="anthropic",
            format_choice="anthropic",
            endpoint="https://api.anthropic.com",
            auth_field="api_key",
            credential="sk-test",
            env_key_arg="env_999",
        )


def test_reuse_existing_env_no_credential_storage():
    """复用已有 env 时不存储凭据"""
    existing_env = _make_env_config(models={"model_1": "existing-model"})
    manager = _make_manager(envs={"env_1": existing_env})
    inputs = ["new-model", "n"]
    # helper 内部 from illusion.auth.storage import store_env_credential
    # 因此 patch 源模块
    with (
        patch("builtins.input", side_effect=inputs),
        patch("illusion.auth.storage.store_env_credential") as mock_store,
    ):
        result = _prompt_models_and_env(
            manager=manager,
            api_format="anthropic",
            format_choice="anthropic",
            endpoint="https://api.anthropic.com",
            auth_field="api_key",
            credential="sk-new",
            env_key_arg="env_1",
        )
    assert result == "env_1"
    # 复用 env 时不调用 store_env_credential
    mock_store.assert_not_called()
