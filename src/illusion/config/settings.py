"""
Settings 模型和加载逻辑模块
===========================

本模块提供 IllusionCode 的设置管理功能，包括：
- Settings: 主设置模型（env_N 分组格式）
- EnvConfig: 环境/提供商组配置
- 各种设置加载和保存函数

设置解析优先级（从高到低）：
    1. CLI 参数
    2. 环境变量（ANTHROPIC_API_KEY, ANTHROPIC_MODEL 等）
    3. 配置文件（~/.illusion/settings.json）
    4. 默认值

类说明：
    - Settings: 主设置模型，使用 env_N 分组管理多个环境配置
    - EnvConfig: 单个环境的配置（api_format, base_url, api_key, model_N 等）
    - PermissionSettings: 权限模式配置
    - MemorySettings: 记忆系统配置
    - SandboxSettings: 沙箱运行时配置

使用示例：
    >>> from illusion.config.settings import load_settings, Settings
    >>> settings = load_settings()
    >>> print(f"当前模型: {settings.active_model_name}")
"""

from __future__ import annotations

import json  # 导入 json 模块用于配置文件读写
import os  # 导入 os 模块用于环境变量访问
from dataclasses import dataclass  # 导入 dataclass 用于创建不可变数据结构
from pathlib import Path  # 导入 Path 用于路径处理
from typing import Any  # 导入 Any 类型用于泛型

from pydantic import BaseModel, Field  # 导入 pydantic 模型基类

from illusion.hooks.schemas import HookDefinition  # 导入钩子定义
from illusion.mcp.types import McpServerConfig  # 导入 MCP 服务器配置
from illusion.permissions.modes import PermissionMode  # 导入权限模式


class PathRuleConfig(BaseModel):
    """路径权限规则配置
    
    使用 glob 模式定义路径级别的权限规则。
    
    Attributes:
        pattern: glob 模式字符串
        allow: 是否允许访问，默认为 True
    """

    pattern: str  # glob 模式，用于匹配路径
    allow: bool = True  # 默认为允许访问


class PermissionSettings(BaseModel):
    """权限模式配置
    
    配置系统的权限控制和行为限制。
    
    Attributes:
        mode: 权限模式
        allowed_tools: 允许的工具列表
        denied_tools: 拒绝的工具列表
        path_rules: 路径规则列表
        denied_commands: 拒绝的命令列表
    """

    mode: PermissionMode = PermissionMode.DEFAULT  # 权限模式，默认为默认模式
    allowed_tools: list[str] = Field(default_factory=list)  # 允许的工具列表
    denied_tools: list[str] = Field(default_factory=list)  # 拒绝的工具列表
    path_rules: list[PathRuleConfig] = Field(default_factory=list)  # 路径权限规则
    denied_commands: list[str] = Field(default_factory=list)  # 拒绝的命令列表


class MemorySettings(BaseModel):
    """记忆系统配置
    
    配置 AI 记忆系统的行为和限制。
    
    Attributes:
        enabled: 是否启用记忆功能
        max_files: 最大记忆文件数
        max_entrypoint_lines: 最大入口文件行数
    """

    enabled: bool = True  # 默认启用记忆功能
    max_files: int = 5  # 默认最多记忆 5 个文件
    max_entrypoint_lines: int = 200  # 默认入口文件最多 200 行


class SandboxNetworkSettings(BaseModel):
    """沙箱网络限制配置
    
    传递给沙箱运行时的操作系统级网络限制配置。
    
    Attributes:
        allowed_domains: 允许访问的域名列表
        denied_domains: 拒绝访问的域名列表
    """

    allowed_domains: list[str] = Field(default_factory=list)  # 允许的域名
    denied_domains: list[str] = Field(default_factory=list)  # 拒绝的域名


class SandboxFilesystemSettings(BaseModel):
    """沙箱文件系统限制配置
    
    传递给沙箱运行时的操作系统级文件系统限制配置。
    
    Attributes:
        allow_read: 允许读取的路径列表
        deny_read: 拒绝读取的路径列表
        allow_write: 允许写入的路径列表
        deny_write: 拒绝写入的路径列表
    """

    allow_read: list[str] = Field(default_factory=list)  # 允许读取的路径
    deny_read: list[str] = Field(default_factory=list)  # 拒绝读取的路径
    allow_write: list[str] = Field(default_factory=lambda: ["."])  # 默认允许写入当前目录
    deny_write: list[str] = Field(default_factory=list)  # 拒绝写入的路径


class SandboxSettings(BaseModel):
    """沙箱运行时集成配置
    
    配置与沙箱运行时的集成选项。
    
    Attributes:
        enabled: 是否启用沙箱
        fail_if_unavailable: 沙箱不可用时是否失败
        enabled_platforms: 启用的平台列表
        network: 网络限制配置
        filesystem: 文件系统限制配置
    """

    enabled: bool = False  # 默认不启用沙箱
    fail_if_unavailable: bool = False  # 沙箱不可用时不失败
    enabled_platforms: list[str] = Field(default_factory=list)  # 启用的平台
    network: SandboxNetworkSettings = Field(default_factory=SandboxNetworkSettings)  # 网络配置
    filesystem: SandboxFilesystemSettings = Field(default_factory=SandboxFilesystemSettings)  # 文件系统配置


@dataclass(frozen=True)
class ResolvedAuth:
    """规范化的认证材料
    
    用于构造 API 客户端的标准化认证信息。
    
    Attributes:
        provider: 提供商名称
        auth_kind: 认证类型
        value: 认证值
        source: 认证来源
        state: 状态（默认为 "configured"）
    """

    provider: str  # 提供商
    auth_kind: str  # 认证类型（api_key、oauth 等）
    value: str  # 认证值
    source: str  # 来源描述
    state: str = "configured"  # 配置状态


# Claude 别名到实际模型名称的映射字典
_CLAUDE_ALIAS_TARGETS: dict[str, str] = {
    "sonnet": "claude-sonnet-4-6",  # Sonnet 别名
    "opus": "claude-opus-4-6",  # Opus 别名
    "haiku": "claude-haiku-4-5",  # Haiku 别名
    "sonnet[1m]": "claude-sonnet-4-6[1m]",  # 1M 上下文 Sonnet
    "opus[1m]": "claude-opus-4-6[1m]",  # 1M 上下文 Opus
}


def normalize_anthropic_model_name(model: str) -> str:
    """标准化 Anthropic 模型名称
    
    与 Hermes 一样标准化模型名称：
    - 去除 "anthropic/" 前缀（如果存在）
    - 将点分隔的 Claude 版本号转换为 Anthropic 的连字符形式
    
    Args:
        model: 原始模型名称
    
    Returns:
        str: 标准化后的模型名称
    """
    normalized = model.strip()  # 去除首尾空白
    lower = normalized.lower()  # 转换为小写用于比较
    # 去除 anthropic/ 前缀
    if lower.startswith("anthropic/"):
        normalized = normalized[len("anthropic/"):]
        lower = normalized.lower()
    # 如果以 claude- 开头，将点转换为连字符
    if lower.startswith("claude-"):
        return normalized.replace(".", "-")
    return normalized


def is_claude_family_provider(provider: str) -> bool:
    """返回该提供商是否为 Claude/Anthropic 工作流
    
    Args:
        provider: 提供商标识符
    
    Returns:
        bool: 是否为 Claude 家族提供商
    """
    return provider in {"anthropic", "anthropic_claude"}


def resolve_model_setting(
    model_setting: str,
    provider: str,
    *,
    default_model: str | None = None,
    permission_mode: str | None = None,
) -> str:
    """将用户面向的模型设置解析为具体的运行时模型 ID
    
    Args:
        model_setting: 用户配置的模型名称或别名
        provider: 提供商标识符
        default_model: 可选的默认模型
        permission_mode: 可选的权限模式
    
    Returns:
        str: 解析后的具体模型 ID
    """
    configured = model_setting.strip()  # 去除空白
    normalized = configured.lower()  # 转换为小写

    # 处理 "default" 或空值
    if not configured or normalized == "default":
        fallback = (default_model or "").strip()  # 获取备用模型
        if fallback and fallback.lower() != "default":
            # 递归解析备用模型
            return resolve_model_setting(
                fallback,
                provider,
                default_model=None,
                permission_mode=permission_mode,
            )
        # Claude 家族默认使用 sonnet
        if is_claude_family_provider(provider):
            return _CLAUDE_ALIAS_TARGETS["sonnet"]
        return "gpt-5.4"

    # 处理 Claude 家族提供商的别名
    if is_claude_family_provider(provider):
        if normalized == "best":
            return _CLAUDE_ALIAS_TARGETS["opus"]  # best 返回 opus
        if normalized == "opusplan":
            # 根据权限模式决定使用 opus 还是 sonnet
            if permission_mode == PermissionMode.PLAN.value:
                return _CLAUDE_ALIAS_TARGETS["opus"]
            return _CLAUDE_ALIAS_TARGETS["sonnet"]
        if normalized in _CLAUDE_ALIAS_TARGETS:
            return _CLAUDE_ALIAS_TARGETS[normalized]  # 直接映射别名
        return normalize_anthropic_model_name(configured)  # 标准化模型名

    # 处理 OpenAI 系列提供商的 default/best
    if provider in {"openai", "openai_codex"} and normalized in {"default", "best"}:
        return "gpt-5.4"

    return configured  # 直接返回原始配置


def auth_source_provider_name(auth_source: str) -> str:
    """将认证来源映射到存储/运行时提供商名称
    
    Args:
        auth_source: 认证来源标识符
    
    Returns:
        str: 映射后的提供商名称
    """
    mapping = {
        "anthropic_api_key": "anthropic",  # Anthropic API 密钥
        "openai_api_key": "openai",  # OpenAI API 密钥
        "codex_subscription": "openai_codex",  # Codex 订阅
        "claude_subscription": "anthropic_claude",  # Claude 订阅
        "dashscope_api_key": "dashscope",  # 阿里 DashScope
        "bedrock_api_key": "bedrock",  # AWS Bedrock
        "vertex_api_key": "vertex",  # Google Vertex
    }
    return mapping.get(auth_source, auth_source)


def default_auth_source_for_provider(provider: str, api_format: str | None = None) -> str:
    """推断提供商的默认认证来源
    
    Args:
        provider: 提供商标识符
        api_format: 可选的 API 格式
    
    Returns:
        str: 默认认证来源
    """
    if provider == "anthropic_claude":
        return "claude_subscription"
    if provider == "openai_codex":
        return "codex_subscription"
    if provider == "dashscope":
        return "dashscope_api_key"
    if provider == "bedrock":
        return "bedrock_api_key"
    if provider == "vertex":
        return "vertex_api_key"
    if provider == "openai" or api_format == "openai":
        return "openai_api_key"
    return "anthropic_api_key"


class EnvConfig(BaseModel):
    """环境/提供商组配置"""
    api_format: str  # "anthropic" / "openai"
    base_url: str | None = None
    api_key: str = ""
    system_prompt: str | None = None

    model_config = {"extra": "allow"}  # 允许 model_N 动态字段

    def get_model(self, model_key: str) -> str | None:
        """获取指定的模型名称，如 model_1, model_2"""
        return getattr(self, model_key, None)

    def list_models(self) -> dict[str, str]:
        """列出所有 model_N 字段"""
        result = {}
        extras = self.model_extra or {}
        for key, value in extras.items():
            if key.startswith("model_") and isinstance(value, str):
                result[key] = value
        return result


class Settings(BaseModel):
    """IllusionCode 主设置模型（env_N 分组格式）"""

    model_config = {"extra": "allow"}  # 允许 env_N 动态字段

    # 活跃模型引用（格式：env_N:model_N）
    model: str = "env_1:model_1"

    # 全局配置
    context_window: int = 200_000
    system_prompt: str | None = None

    # 保留的非模型字段
    max_tokens: int = 16384
    max_turns: int = 200
    permission: PermissionSettings = Field(default_factory=PermissionSettings)
    hooks: dict[str, list[HookDefinition]] = Field(default_factory=dict)
    memory: MemorySettings = Field(default_factory=MemorySettings)
    sandbox: SandboxSettings = Field(default_factory=SandboxSettings)
    enabled_plugins: dict[str, bool] = Field(default_factory=dict)
    mcp_servers: dict[str, McpServerConfig] = Field(default_factory=dict)
    ui_language: str = "zh-CN"
    output_style: str = "default"
    fast_mode: bool = False
    effort: str = "medium"
    passes: int = 1
    verbose: bool = False

    # --- env_N 配置辅助方法 ---

    def get_env(self, env_key: str) -> EnvConfig | None:
        """获取指定的环境配置"""
        value = getattr(self, env_key, None)
        if isinstance(value, dict):
            return EnvConfig.model_validate(value)
        return value if isinstance(value, EnvConfig) else None

    def list_envs(self) -> dict[str, EnvConfig]:
        """列出所有 env_N 配置"""
        result = {}
        extras = self.model_extra or {}
        for key, value in extras.items():
            if key.startswith("env_"):
                if isinstance(value, EnvConfig):
                    result[key] = value
                elif isinstance(value, dict):
                    result[key] = EnvConfig.model_validate(value)
        return result

    @property
    def _active_env_key(self) -> str:
        """解析 model 字段，返回 env key"""
        if ":" in self.model:
            return self.model.split(":", 1)[0]
        return "env_1"

    @property
    def _active_model_key(self) -> str:
        """解析 model 字段，返回 model key"""
        if ":" in self.model:
            return self.model.split(":", 1)[1]
        return "model_1"

    @property
    def _active_env(self) -> EnvConfig:
        """返回当前活跃的环境配置"""
        env = self.get_env(self._active_env_key)
        if env is None:
            envs = self.list_envs()
            if envs:
                return next(iter(envs.values()))
            return EnvConfig(api_format="anthropic")
        return env

    @property
    def _active_model_name(self) -> str:
        """返回当前活跃的模型名称"""
        env = self._active_env
        model_name = env.get_model(self._active_model_key)
        if model_name is None:
            models = env.list_models()
            if models:
                return next(iter(models.values()))
            return "claude-sonnet-4-6"
        return model_name

    # --- 兼容性属性 ---

    @property
    def active_model_name(self) -> str:
        """兼容性属性：当前活跃模型名称"""
        return self._active_model_name

    @property
    def api_key(self) -> str:
        """兼容性属性：当前活跃环境的 API 密钥"""
        return self._active_env.api_key

    @property
    def base_url(self) -> str | None:
        """兼容性属性：当前活跃环境的 base URL"""
        return self._active_env.base_url

    @property
    def provider(self) -> str:
        """兼容性属性：根据 api_format 推断提供商"""
        fmt = self._active_env.api_format
        if fmt == "anthropic":
            return "anthropic"
        return "openai"

    @property
    def api_format(self) -> str:
        """兼容性属性：当前活跃环境的 API 格式"""
        return self._active_env.api_format

    def resolve_api_key(self) -> str:
        """解析 API 密钥

        优先级：EnvConfig.api_key > 环境变量 > 空

        Returns:
            str: API 密钥字符串

        Raises:
            ValueError: 未找到密钥时抛出
        """
        env = self._active_env

        # 检查 EnvConfig 中的 api_key
        if env.api_key:
            return env.api_key

        # 检查环境变量 ANTHROPIC_API_KEY
        env_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if env_key:
            return env_key

        # 对于 openai 格式的提供商，也检查 OPENAI_API_KEY
        openai_key = os.environ.get("OPENAI_API_KEY", "")
        if openai_key:
            return openai_key

        raise ValueError(
            "No API key found. Set ANTHROPIC_API_KEY (or OPENAI_API_KEY for openai-format "
            "providers) environment variable, or configure api_key in "
            "~/.illusion/settings.json"
        )

    def resolve_auth(self) -> ResolvedAuth:
        """解析当前活跃环境的认证信息

        Returns:
            ResolvedAuth: 解析后的认证对象

        Raises:
            ValueError: 认证配置错误时抛出
        """
        env = self._active_env
        provider = self.provider  # 从 api_format 推断
        api_format = env.api_format
        auth_source = default_auth_source_for_provider(provider, api_format)

        # 检查 EnvConfig 中的 api_key
        if env.api_key:
            return ResolvedAuth(
                provider=provider,
                auth_kind="api_key",
                value=env.api_key,
                source="env_config",
                state="configured",
            )

        # 检查环境变量
        env_var_map = {
            "anthropic_api_key": "ANTHROPIC_API_KEY",
            "openai_api_key": "OPENAI_API_KEY",
            "dashscope_api_key": "DASHSCOPE_API_KEY",
        }
        env_var = env_var_map.get(auth_source)
        if env_var:
            env_value = os.environ.get(env_var, "")
            if env_value:
                return ResolvedAuth(
                    provider=provider,
                    auth_kind="api_key",
                    value=env_value,
                    source=f"env:{env_var}",
                    state="configured",
                )

        # 从文件存储加载
        from illusion.auth.storage import load_credential

        storage_provider = auth_source_provider_name(auth_source)
        stored = load_credential(storage_provider, "api_key")
        if stored:
            return ResolvedAuth(
                provider=provider,
                auth_kind="api_key",
                value=stored,
                source=f"file:{storage_provider}",
                state="configured",
            )

        raise ValueError(
            f"No credentials found for auth source '{auth_source}'. "
            "Configure the matching provider or environment variable first."
        )

    def merge_cli_overrides(self, **overrides: Any) -> Settings:
        """返回应用了 CLI 覆盖的新 Settings（仅非 None 值）

        Args:
            **overrides: 要覆盖的字段

        Returns:
            Settings: 应用覆盖后的新实例
        """
        updates = {k: v for k, v in overrides.items() if v is not None}
        if not updates:
            return self
        return self.model_copy(update=updates)


def _apply_env_overrides(settings: Settings) -> Settings:
    """在加载的设置上应用环境变量覆盖到活跃的 EnvConfig

    直接修改活跃 env 的 api_key、model、base_url 等字段，
    而不是设置 Settings 的属性（属性会 shadow extras）。

    Args:
        settings: 原始设置

    Returns:
        Settings: 应用环境变量覆盖后的设置
    """
    env = settings._active_env
    env_modified = False

    model = os.environ.get("ANTHROPIC_MODEL")
    if model:
        env.model = model
        env_modified = True

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        env.api_key = api_key
        env_modified = True

    base_url = os.environ.get("ANTHROPIC_BASE_URL")
    if base_url:
        env.base_url = base_url
        env_modified = True

    # 非模型相关的全局字段覆盖仍使用 model_copy
    updates: dict[str, Any] = {}

    max_tokens = os.environ.get("illusion_MAX_TOKENS")
    if max_tokens:
        updates["max_tokens"] = int(max_tokens)

    max_turns = os.environ.get("illusion_MAX_TURNS")
    if max_turns:
        updates["max_turns"] = int(max_turns)

    sandbox_enabled = os.environ.get("illusion_SANDBOX_ENABLED")
    sandbox_fail = os.environ.get("illusion_SANDBOX_FAIL_IF_UNAVAILABLE")
    sandbox_updates: dict[str, Any] = {}
    if sandbox_enabled is not None:
        sandbox_updates["enabled"] = _parse_bool_env(sandbox_enabled)
    if sandbox_fail is not None:
        sandbox_updates["fail_if_unavailable"] = _parse_bool_env(sandbox_fail)
    if sandbox_updates:
        updates["sandbox"] = settings.sandbox.model_copy(update=sandbox_updates)

    # 将修改后的 env 写回 settings 的 extras
    if env_modified:
        env_key = settings._active_env_key
        updates[env_key] = env

    if not updates:
        return settings
    return settings.model_copy(update=updates)


def _parse_bool_env(value: str) -> bool:
    """解析布尔环境变量

    Args:
        value: 环境变量值字符串

    Returns:
        bool: 解析后的布尔值
    """
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_settings(config_path: Path | None = None) -> Settings:
    """从配置文件加载设置

    Args:
        config_path: settings.json 的路径。如果为 None，使用默认位置。

    Returns:
        Settings: 应用环境变量覆盖后的 Settings 实例
    """
    if config_path is None:
        from illusion.config.paths import get_config_file_path

        config_path = get_config_file_path()

    if config_path.exists():
        raw = json.loads(config_path.read_text(encoding="utf-8"))
        settings = Settings.model_validate(raw)
        return _apply_env_overrides(settings)

    return _apply_env_overrides(Settings())


def save_settings(settings: Settings, config_path: Path | None = None) -> None:
    """将设置持久化到配置文件

    Args:
        settings: 要保存的 Settings 实例
        config_path: 写入路径。如果为 None，使用默认位置
    """
    if config_path is None:
        from illusion.config.paths import get_config_file_path

        config_path = get_config_file_path()

    config_path.parent.mkdir(parents=True, exist_ok=True)

    # 序列化并重排字段，env_N 置顶
    data = settings.model_dump()
    ordered: dict[str, object] = {}
    for key in sorted(data):
        if key.startswith("env_"):
            ordered[key] = data[key]
    for key, value in data.items():
        if not key.startswith("env_"):
            ordered[key] = value

    config_path.write_text(
        json.dumps(ordered, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
