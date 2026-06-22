"""沙箱工具函数测试"""
from illusion.sandbox.utils import (
    encode_sandboxed_command,
    decode_sandboxed_command,
    contains_glob_chars,
    remove_trailing_glob_suffix,
    normalize_case_for_comparison,
    generate_proxy_env_vars,
    get_default_write_paths,
)


def test_encode_decode_command():
    cmd = "rm -rf /tmp/test"
    encoded = encode_sandboxed_command(cmd)
    assert isinstance(encoded, str)
    decoded = decode_sandboxed_command(encoded)
    assert decoded == cmd[:100]


def test_encode_truncates_long_command():
    cmd = "a" * 200
    encoded = encode_sandboxed_command(cmd)
    decoded = decode_sandboxed_command(encoded)
    assert len(decoded) == 100


def test_contains_glob_chars():
    assert contains_glob_chars("*.txt") is True
    assert contains_glob_chars("path/to/file") is False
    assert contains_glob_chars("path/[abc]") is True
    assert contains_glob_chars("path/?ile") is True


def test_remove_trailing_glob_suffix():
    assert remove_trailing_glob_suffix("path/**") == "path"
    assert remove_trailing_glob_suffix("path/to/file") == "path/to/file"


def test_normalize_case():
    assert normalize_case_for_comparison("/Path/To/File") == "/path/to/file"


def test_generate_proxy_env_vars():
    env = generate_proxy_env_vars(8080, 1080)
    assert "HTTP_PROXY" in env
    assert "8080" in env["HTTP_PROXY"]
    assert "HTTPS_PROXY" in env
    assert "ALL_PROXY" in env
    assert "1080" in env["ALL_PROXY"]
    assert "NO_PROXY" in env
    assert "localhost" in env["NO_PROXY"]


def test_default_write_paths():
    paths = get_default_write_paths()
    assert "/dev/null" in paths
    assert "/dev/stdout" in paths
    assert any("tmp" in p for p in paths)
