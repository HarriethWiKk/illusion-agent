"""CLI smoke tests."""

from typer.testing import CliRunner

from illusion.cli import app


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Illusion Code" in result.output


def test_continue_flag_passed_to_backend_command(monkeypatch):
    """-c 标志应传递给子进程的 --backend-only 命令。"""
    from illusion.ui.react_launcher import build_backend_command

    cmd = build_backend_command(cwd="/tmp", continue_session=True)
    assert "--continue" in cmd
    assert "--backend-only" in cmd


def test_resume_flag_passed_to_backend_command():
    """--resume 标志应传递给子进程。"""
    from illusion.ui.react_launcher import build_backend_command

    cmd = build_backend_command(cwd="/tmp", resume="abc123")
    assert "--resume" in cmd
    assert "abc123" in cmd


def test_settings_file_passed_to_load_settings(tmp_path, monkeypatch):
    """--settings 指定的文件应被 load_settings 加载。"""
    import json
    settings_file = tmp_path / "custom_settings.json"
    settings_file.write_text(json.dumps({"model": "env_1.model_custom"}))

    from illusion.config.settings import load_settings
    # 验证 load_settings 接受 config_path 参数
    settings = load_settings(config_path=settings_file)
    assert settings.model == "env_1.model_custom"
