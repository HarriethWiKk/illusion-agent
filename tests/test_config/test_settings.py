"""Tests for illusion.config.settings."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from illusion.config.settings import (
    Settings,
    load_settings,
    normalize_anthropic_model_name,
    save_settings,
)


class TestSettings:
    def test_defaults(self):
        s = Settings()
        assert s.api_key == ""
        assert s.model == "env_1:model_1"
        assert s.active_model_name == "claude-sonnet-4-6"
        assert s.max_tokens == 16384
        assert s.max_turns == 200
        assert s.fast_mode is False
        assert s.permission.mode == "default"
        assert s.sandbox.enabled is False
        assert s.sandbox.filesystem.allow_write == ["."]

    def test_resolve_api_key_from_env_config(self):
        s = Settings(env_1={"api_format": "anthropic", "api_key": "sk-test-123"})
        assert s.resolve_api_key() == "sk-test-123"

    def test_resolve_api_key_from_env_var(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env-456")
        s = Settings()
        assert s.resolve_api_key() == "sk-env-456"

    def test_resolve_api_key_env_config_takes_precedence(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env-456")
        s = Settings(env_1={"api_format": "anthropic", "api_key": "sk-instance-789"})
        assert s.resolve_api_key() == "sk-instance-789"

    def test_resolve_api_key_missing_raises(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        s = Settings()
        with pytest.raises(ValueError, match="No API key found"):
            s.resolve_api_key()

    def test_resolve_api_key_copilot(self):
        s = Settings(env_1={"api_format": "copilot"})
        assert s.resolve_api_key() == "copilot-managed"

    def test_merge_cli_overrides(self):
        s = Settings()
        updated = s.merge_cli_overrides(model="env_2:model_1", verbose=True, api_key=None)
        assert updated.model == "env_2:model_1"
        assert updated.verbose is True

    def test_merge_cli_overrides_returns_new_instance(self):
        s = Settings()
        updated = s.merge_cli_overrides(model="env_2:model_1")
        assert s.model != updated.model
        assert s is not updated

    def test_active_env_properties(self):
        s = Settings(
            env_1={"api_format": "openai", "api_key": "sk-test", "base_url": "https://api.example.com"},
        )
        assert s.api_format == "openai"
        assert s.api_key == "sk-test"
        assert s.base_url == "https://api.example.com"
        assert s.provider == "openai"

    def test_active_model_name_from_env(self):
        s = Settings(
            model="env_1:model_1",
            env_1={"api_format": "anthropic", "model_1": "claude-opus-4-20250514"},
        )
        assert s.active_model_name == "claude-opus-4-20250514"

    def test_active_model_name_fallback(self):
        """When no env config is set, active_model_name falls back to claude-sonnet-4-6"""
        s = Settings()
        assert s.active_model_name == "claude-sonnet-4-6"


class TestLoadSaveSettings:
    def test_load_missing_file_returns_defaults(self, tmp_path: Path, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
        monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        path = tmp_path / "nonexistent.json"
        s = load_settings(path)
        assert s.model == "env_1:model_1"
        assert s.active_model_name == "claude-sonnet-4-6"
        assert s.max_tokens == 16384

    def test_load_existing_file(self, tmp_path: Path):
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({
            "model": "env_1:model_1",
            "env_1": {"api_format": "anthropic", "model_1": "claude-opus-4-20250514"},
            "verbose": True,
            "fast_mode": True,
        }))
        s = load_settings(path)
        assert s.active_model_name == "claude-opus-4-20250514"
        assert s.verbose is True
        assert s.fast_mode is True
        assert s.api_key == ""

    def test_save_and_load_roundtrip(self, tmp_path: Path):
        path = tmp_path / "settings.json"
        original = Settings(
            env_1={"api_format": "anthropic", "api_key": "sk-roundtrip", "model_1": "claude-opus-4-20250514"},
            verbose=True,
        )
        save_settings(original, path)
        loaded = load_settings(path)
        assert loaded.api_key == "sk-roundtrip"
        assert loaded.active_model_name == "claude-opus-4-20250514"
        assert loaded.verbose is True

    def test_save_creates_parent_dirs(self, tmp_path: Path):
        path = tmp_path / "deep" / "nested" / "settings.json"
        save_settings(Settings(), path)
        assert path.exists()

    def test_load_with_permission_settings(self, tmp_path: Path):
        path = tmp_path / "settings.json"
        path.write_text(
            json.dumps(
                {
                    "permission": {
                        "mode": "full_auto",
                        "allowed_tools": ["Bash", "Read"],
                    }
                }
            )
        )
        s = load_settings(path)
        assert s.permission.mode == "full_auto"
        assert s.permission.allowed_tools == ["Bash", "Read"]

    def test_load_applies_env_overrides(self, tmp_path: Path, monkeypatch):
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({
            "model": "env_1:model_1",
            "env_1": {"api_format": "anthropic", "model_1": "from-file"},
        }))
        monkeypatch.setenv("ANTHROPIC_MODEL", "from-env-model")
        monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://env.example/anthropic")
        monkeypatch.setenv("illusion_MAX_TURNS", "42")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env-override")
        monkeypatch.setenv("illusion_SANDBOX_ENABLED", "true")
        monkeypatch.setenv("illusion_SANDBOX_FAIL_IF_UNAVAILABLE", "1")

        s = load_settings(path)

        # env overrides go into the active env config
        assert s._active_env.model == "from-env-model"
        assert s._active_env.base_url == "https://env.example/anthropic"
        assert s._active_env.api_key == "sk-env-override"
        # global overrides
        assert s.max_turns == 42
        assert s.sandbox.enabled is True
        assert s.sandbox.fail_if_unavailable is True

    def test_load_with_sandbox_settings(self, tmp_path: Path):
        path = tmp_path / "settings.json"
        path.write_text(
            json.dumps(
                {
                    "sandbox": {
                        "enabled": True,
                        "enabled_platforms": ["linux", "wsl"],
                        "network": {"allowed_domains": ["github.com"]},
                        "filesystem": {"allow_write": [".", "/tmp"], "deny_write": [".env"]},
                    }
                }
            )
        )

        s = load_settings(path)

        assert s.sandbox.enabled is True
        assert s.sandbox.enabled_platforms == ["linux", "wsl"]
        assert s.sandbox.network.allowed_domains == ["github.com"]
        assert s.sandbox.filesystem.allow_write == [".", "/tmp"]
        assert s.sandbox.filesystem.deny_write == [".env"]

    def test_load_with_env_config(self, tmp_path: Path):
        """Test loading a file that uses the new env_N format."""
        path = tmp_path / "settings.json"
        path.write_text(
            json.dumps(
                {
                    "model": "env_1:model_1",
                    "env_1": {
                        "api_format": "anthropic",
                        "api_key": "sk-test",
                        "model_1": "claude-sonnet-4-6",
                        "model_2": "claude-opus-4-6",
                    },
                }
            )
        )

        s = load_settings(path)
        assert s.api_key == "sk-test"
        assert s.active_model_name == "claude-sonnet-4-6"
        assert s.provider == "anthropic"

    def test_save_preserves_env_config(self, tmp_path: Path):
        """Test that save/load roundtrip preserves env_N config."""
        path = tmp_path / "settings.json"
        original = Settings(
            model="env_1:model_2",
            env_1={
                "api_format": "openai",
                "api_key": "sk-test",
                "model_1": "gpt-4",
                "model_2": "gpt-5.4",
            },
        )
        save_settings(original, path)
        loaded = load_settings(path)
        assert loaded.active_model_name == "gpt-5.4"
        assert loaded.api_key == "sk-test"


def test_normalize_anthropic_model_name_matches_hermes_behavior():
    assert normalize_anthropic_model_name("anthropic/claude-sonnet-4-20250514") == "claude-sonnet-4-20250514"
    assert normalize_anthropic_model_name("claude-opus-4.6") == "claude-opus-4-6"
