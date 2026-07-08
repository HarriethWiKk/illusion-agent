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
