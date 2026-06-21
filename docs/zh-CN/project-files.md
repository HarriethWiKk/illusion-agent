# 项目指令文件与记忆文件

## AI 指令文件 (CLAUDE.md / ILLUSION.md / AGENTS.md)

`CLAUDE.md`、`ILLUSION.md` 和 `AGENTS.md` 是**等效的** AI 指令文件。IllusionCode 识别这三个名称，行为完全一致。

### 发现位置

系统在以下位置扫描这些文件（仅在当前工作目录内，**不在** `~/.illusion/` 全局目录中）：

1. **项目根目录**：`{cwd}/CLAUDE.md`、`{cwd}/AGENTS.md`、`{cwd}/ILLUSION.md`
2. **`.claude/` 目录**：`{cwd}/.claude/CLAUDE.md`
3. **`.illusion/` 目录**：`{cwd}/.illusion/CLAUDE.md`、`{cwd}/.illusion/AGENTS.md`、`{cwd}/.illusion/ILLUSION.md`

所有发现的文件合并为系统提示词中的 `# Project Instructions` 部分。每个文件限制 12,000 字符（超出部分截断）。

### 规则文件

除上述指令文件外，系统还扫描：

- `{cwd}/.claude/rules/*.md` — 按文件名排序，每个文件是独立的规则

### 使用方法

在项目根目录创建任一文件，提供项目特定的上下文和指令：

```markdown
# 项目说明

这是一个 Python Web 项目，使用 FastAPI 框架。

## 代码规范

- 使用 Python 3.10+ 特性
- 遵循 PEP 8 代码风格
- 使用 type hints

## 目录结构

- src/api: API 路由
- src/models: 数据模型
- src/services: 业务逻辑

## 注意事项

- 不要修改 tests/ 目录下的文件
- 提交前运行 pytest
```

### 源码参考

文件发现逻辑：`src/illusion/prompts/claudemd.py` — `discover_claude_md_files()` 函数。

---

## 记忆文件 (MEMORY.md)

记忆系统通过 `MEMORY.md` 和关联的记忆文件提供项目知识持久化功能。

### 存储位置

记忆文件存储在两个位置，项目级位置优先：

1. **项目级**（优先）：`{cwd}/.illusion/memory/`
2. **全局回退**：`~/.illusion/data/memory/{项目名}-{sha1哈希前12位}/`

全局回退的目录名格式为 `{path.name}-{sha1(path)[:12]}`。

### MEMORY.md 入口文件

`MEMORY.md` 是入口索引文件，每条记录是一行指针：

```markdown
- [标题](文件名.md) — 一行描述
- [另一个主题](另一个文件.md) — 另一行描述
```

**限制：**
- 最大 200 行（由 `memory.max_entrypoint_lines` 控制）
- 最大 5 个记忆文件（由 `memory.max_files` 控制）

### 记忆文件格式

每个记忆文件使用 frontmatter 格式：

```markdown
---
name: short-kebab-case-slug
description: 一行摘要，用于相关性匹配
metadata:
  type: user|feedback|project|reference
---

记忆条目的内容。
```

### 记忆类型

| 类型 | 用途 |
|------|------|
| `user` | 用户角色、目标、偏好、知识水平 |
| `feedback` | 工作方式指导（纠正和确认） |
| `project` | 进行中的工作、目标、计划、Bug、事件 |
| `reference` | 外部系统指针（Linear、Slack、Grafana 等） |

### 记忆管理

记忆条目可通过以下方式管理：
- 交互式会话中的 `/memory` 斜杠命令
- `remember` 技能
- 直接编辑记忆目录中的文件

### 初始化

`/init` 命令在 `{cwd}/.illusion/memory/MEMORY.md` 创建初始模板。

### 源码参考

- 路径解析：`src/illusion/memory/paths.py`
- 加载逻辑：`src/illusion/memory/memdir.py`
- 管理功能：`src/illusion/memory/manager.py`

---

## 项目级权限配置 (permissions.json)

项目级 `permissions.json` 文件位于 `<project>/.illusion/permissions.json`，用于控制该项目的权限和禁用开关。

### 配置示例

```json
{
  "always_allow_tools": ["read_file", "grep"],
  "denied_tools": ["bash"],
  "denied_skills": ["dangerous-skill"],
  "denied_hooks": ["PreToolUse"],
  "denied_plugins": ["unwanted-plugin"],
  "denied_mcp_servers": ["external-server"],
  "denied_memory": false
}
```

### 配置字段说明

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `always_allow_tools` | list | `[]` | 始终允许的工具列表 |
| `denied_tools` | list | `[]` | 始终拒绝的工具列表 |
| `denied_skills` | list | `[]` | 禁用的 skill 名称列表，`["*"]` 表示全部禁用 |
| `denied_hooks` | list | `[]` | 禁用的 hook 事件列表，`["*"]` 表示全部禁用 |
| `denied_plugins` | list | `[]` | 禁用的插件名称列表，`["*"]` 表示全部禁用 |
| `denied_mcp_servers` | list | `[]` | 禁用的 MCP 服务器名称列表，`["*"]` 表示全部禁用 |
| `denied_memory` | bool | `false` | 是否禁用 memory 功能 |
| `denied_rules` | list | `[]` | 禁用的规则名称列表，`["*"]` 表示全部禁用 |

### 优先级规则

1. 项目级 `permissions.json` — 最高优先级
2. 全局 `settings.json` — 次优先级
3. 默认值 — 最低优先级

### 源码参考

- 权限加载器：`src/illusion/permissions/loader.py`
- 权限数据类：`src/illusion/permissions/schemas.py`
