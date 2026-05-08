from __future__ import annotations

import base64
import json
from pathlib import Path

from illusion.auth.external import (
    CLAUDE_PROVIDER,
    CODEX_PROVIDER,
    ExternalAuthState,
    describe_external_binding,
    default_binding_for_provider,
    get_claude_code_version,
    load_external_credential,
    refresh_claude_oauth_credential,
)
from illusion.auth.storage import ExternalAuthBinding, load_external_binding, store_external_binding
from illusion.config.settings import Settings, load_settings, save_settings


def _b64url(data: dict[str, object]) -> str:
    raw = json.dumps(data, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _fake_jwt(payload: dict[str, object]) -> str:
    return f"{_b64url({'alg': 'none', 'typ': 'JWT'})}.{_b64url(payload)}.sig"


def test_load_codex_external_credential(monkeypatch, tmp_path: Path):
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    token = _fake_jwt(
        {
            "exp": 4_102_444_800,
            "https://api.openai.com/profile": {"email": "dev@example.com"},
        }
    )
    (codex_home / "auth.json").write_text(
        json.dumps(
            {
                "auth_mode": "chatgpt",
                "tokens": {
                    "access_token": token,
                    "refresh_token": "refresh-token",
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    binding = default_binding_for_provider(CODEX_PROVIDER)
    credential = load_external_credential(binding)

    assert credential.provider == CODEX_PROVIDER
    assert credential.auth_kind == "api_key"
    assert credential.value == token
    assert credential.refresh_token == "refresh-token"
    assert credential.profile_label == "dev@example.com"
    assert credential.expires_at_ms == 4_102_444_800_000


def test_load_claude_external_credential(monkeypatch, tmp_path: Path):
    claude_home = tmp_path / "claude-home"
    claude_home.mkdir()
    (claude_home / ".credentials.json").write_text(
        json.dumps(
            {
                "claudeAiOauth": {
                    "accessToken": "claude-access-token",
                    "refreshToken": "claude-refresh-token",
                    "expiresAt": 4_102_444_800_000,
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CLAUDE_HOME", str(claude_home))

    binding = default_binding_for_provider(CLAUDE_PROVIDER)
    credential = load_external_credential(binding)

    assert credential.provider == CLAUDE_PROVIDER
    assert credential.auth_kind == "auth_token"
    assert credential.value == "claude-access-token"
    assert credential.refresh_token == "claude-refresh-token"
    assert credential.expires_at_ms == 4_102_444_800_000


def test_settings_resolve_auth_uses_env_config(monkeypatch, tmp_path: Path):
    """resolve_auth() should use api_key from the active env config."""
    config_dir = tmp_path / "config"
    monkeypatch.setenv("illusion_CONFIG_DIR", str(config_dir))

    settings = Settings(
        model="env_1:model_1",
        env_1={"api_format": "anthropic", "api_key": "env-config-key"},
    )
    resolved = settings.resolve_auth()

    assert resolved.auth_kind == "api_key"
    assert resolved.value == "env-config-key"


def test_external_binding_for_codex_without_switching(monkeypatch, tmp_path: Path):
    """Binding a Codex external credential should not change the active model/env config."""
    config_dir = tmp_path / "config"
    codex_home = tmp_path / "codex-home"
    config_dir.mkdir()
    codex_home.mkdir()
    token = _fake_jwt({"exp": 4_102_444_800})
    (codex_home / "auth.json").write_text(
        json.dumps(
            {
                "auth_mode": "chatgpt",
                "tokens": {
                    "access_token": token,
                    "refresh_token": "refresh-token",
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("illusion_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)

    (config_dir / "settings.json").write_text(
        json.dumps(
            {
                "model": "env_1:model_1",
                "env_1": {
                    "api_format": "openai",
                    "api_key": "stale-key",
                    "base_url": "https://api.moonshot.cn/anthropic",
                },
            }
        ),
        encoding="utf-8",
    )

    binding = default_binding_for_provider(CODEX_PROVIDER)
    credential = load_external_credential(binding)
    store_external_binding(
        ExternalAuthBinding(
            provider=CODEX_PROVIDER,
            source_path=str(codex_home / "auth.json"),
            source_kind="codex_auth_json",
            managed_by="codex-cli",
            profile_label="Codex CLI",
        )
    )

    settings = load_settings()
    assert settings.model == "env_1:model_1"
    assert settings.provider == "openai"
    assert settings.base_url == "https://api.moonshot.cn/anthropic"
    assert settings.api_key == "stale-key"
    binding = load_external_binding(CODEX_PROVIDER)
    assert binding is not None
    assert Path(binding.source_path) == codex_home / "auth.json"


def test_external_binding_for_claude_without_switching(monkeypatch, tmp_path: Path):
    """Binding a Claude external credential should not change the active model/env config."""
    config_dir = tmp_path / "config"
    claude_home = tmp_path / "claude-home"
    claude_home.mkdir()
    (claude_home / ".credentials.json").write_text(
        json.dumps(
            {
                "claudeAiOauth": {
                    "accessToken": "claude-access-token",
                    "refreshToken": "claude-refresh-token",
                    "expiresAt": 4_102_444_800_000,
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("illusion_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("CLAUDE_HOME", str(claude_home))
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)

    binding = default_binding_for_provider(CLAUDE_PROVIDER)
    credential = load_external_credential(binding)
    store_external_binding(
        ExternalAuthBinding(
            provider=CLAUDE_PROVIDER,
            source_path=str(claude_home / ".credentials.json"),
            source_kind="claude_credentials_json",
            managed_by="claude-cli",
            profile_label="Claude CLI",
        )
    )

    settings = load_settings()
    assert settings.provider == "anthropic"
    assert settings.api_format == "anthropic"
    assert settings.model == "env_1:model_1"
    binding = load_external_binding(CLAUDE_PROVIDER)
    assert binding is not None
    assert Path(binding.source_path) == claude_home / ".credentials.json"


def test_codex_env_activation_via_config(monkeypatch, tmp_path: Path):
    """Activating a Codex env via config should preserve env_N format settings."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    monkeypatch.setenv("illusion_CONFIG_DIR", str(config_dir))
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)

    save_settings(
        Settings(
            model="env_1:model_1",
            env_1={
                "api_format": "openai",
                "api_key": "codex-key",
                "model_1": "gpt-5.4",
            },
        )
    )

    settings = load_settings()
    assert settings.model == "env_1:model_1"
    assert settings.api_format == "openai"
    assert settings.api_key == "codex-key"
    assert settings.active_model_name == "gpt-5.4"


def test_describe_external_binding_reports_refreshable_claude_token(tmp_path: Path):
    source = tmp_path / "claude-credentials.json"
    source.write_text(
        json.dumps(
            {
                "claudeAiOauth": {
                    "accessToken": "expired-token",
                    "refreshToken": "refresh-token",
                    "expiresAt": 1,
                }
            }
        ),
        encoding="utf-8",
    )

    state = describe_external_binding(
        ExternalAuthBinding(
            provider=CLAUDE_PROVIDER,
            source_path=str(source),
            source_kind="claude_credentials_json",
            managed_by="claude-cli",
            profile_label="Claude CLI",
        )
    )

    assert state == ExternalAuthState(
        configured=True,
        state="refreshable",
        source="external",
        detail=f"expired token can be refreshed from {source}",
    )


def test_refresh_claude_oauth_credential(monkeypatch):
    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(
                {
                    "access_token": "fresh-token",
                    "refresh_token": "fresh-refresh",
                    "expires_in": 7200,
                }
            ).encode("utf-8")

    monkeypatch.setattr(
        "illusion.auth.external.urllib.request.urlopen",
        lambda request, timeout=10: _FakeResponse(),
    )
    monkeypatch.setattr("illusion.auth.external.time.time", lambda: 1000)

    refreshed = refresh_claude_oauth_credential("refresh-token")

    assert refreshed["access_token"] == "fresh-token"
    assert refreshed["refresh_token"] == "fresh-refresh"
    assert refreshed["expires_at_ms"] == (1000 * 1000) + (7200 * 1000)


def test_get_claude_code_version_uses_fallback(monkeypatch):
    class _Result:
        returncode = 1
        stdout = ""

    monkeypatch.setattr(
        "illusion.auth.external.subprocess.run",
        lambda *args, **kwargs: _Result(),
    )
    monkeypatch.setattr("illusion.auth.external._claude_code_version_cache", None)

    assert get_claude_code_version() == "2.1.88"
