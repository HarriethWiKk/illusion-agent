# 消息渠道

## 目录

- [工作原理](#工作原理)
- [支持的渠道](#支持的渠道)
- [快速开始（飞书）](#快速开始飞书)
- [渠道配置（channels.json）](#渠道配置channelsjson)
- [飞书侧斜杠命令](#飞书侧斜杠命令)
- [飞书内置工具](#飞书内置工具)
- [权限交互](#权限交互)
- [常见问题排查](#常见问题排查)
- [快速开始（微信）](#快速开始微信)
- [渠道架构](#渠道架构)

---

## 📱 消息渠道

IllusionCode 支持消息渠道，让你能通过飞书（Feishu / Lark）和微信等即时通讯应用与 AI 助手交互。这实现了**远程继续工作**——在终端开始一个任务，然后通过手机继续。

### 工作原理

```
illusion（主程序启动）
 ├─ 读取 channels.json → feishu.enabled / weixin.enabled / qq.enabled
 ├─ 静默后台 spawn 'illusion channel serve' 守护进程
 │    └─ 飞书：WS 长连接 → agent → 流式卡片回复
 │    └─ 微信：HTTP 长轮询 → agent → 打字状态 + 文本回复
 │    └─ QQ：WS 网关 → agent → 文本回复
 └─ run_repl()  ← 本地终端交互（不受影响）

手机
 └─ 发消息 → 守护进程接收 → agent 处理 → 回复
```

### 支持的渠道

| 渠道 | 协议 | 流式输出 | 群聊 | 状态 |
|------|------|----------|------|------|
| 飞书 / Feishu / Lark | WS 长连接 | 交互卡片（JSON 2.0） | ✅ | 生产就绪 |
| 微信（iLink Bot） | HTTP 长轮询 | 打字状态 + 文本 | ❌（仅私聊） | 生产就绪 |
| QQ（QQ 开放平台 Bot） | WS 网关 | 文本 | ✅（C2C + 群聊） | 生产就绪 |

### 快速开始（飞书）

#### 1. 创建飞书应用

1. 访问[飞书开放平台](https://open.feishu.cn/app)（Lark 国际版：[open.larksuite.com](https://open.larksuite.com/app)）
2. 创建**自建应用**
3. 开启**机器人**能力
4. 在**事件订阅**页面，选择**长连接模式**
5. 订阅事件：`im.message.receive_v1`（接收消息）
6. 记录**App ID** 和 **App Secret**

#### 2. 配置渠道

```bash
illusion channel login
```

启动交互式配置向导：

```
选择渠道 / Select a channel:
  1. 飞书 / Feishu (Lark)
输入序号: 1

--- 飞书渠道渠道配置 ---
选择平台 / Select platform:
  1. 飞书 (open.feishu.cn)
  2. Lark (open.larksuite.com)
输入序号: 1

输入 App ID: cli_a1b2c3...
输入 App Secret: 明文输入

是否启用群组会话按用户隔离? (Y/n): Y
群组中是否要求 @机器人才响应? (Y/n): Y
是否允许其他机器人消息? (y/N): N

正在安装依赖 lark-oapi... ✓
配置已保存，飞书渠道已启用。
```

- 首次配置时**自动安装** `lark-oapi` SDK（作为可选依赖）
- 凭据明文存储在 `~/.illusion/channels.json`（按需求不遮掩）
- 下次运行 `illusion` 时**自动激活**渠道

#### 3. 开始使用

```bash
# 方式一：让 illusion 自动激活渠道（静默后台守护进程）
illusion                    # 渠道守护进程自动启动，REPL 正常运行

# 方式二：前台运行守护进程（查看日志，Ctrl+C 停止）
illusion channel serve
```

现在在飞书给机器人发消息，你会收到流式卡片回复，完整渲染 Markdown。

### 渠道配置（channels.json）

渠道配置单独存储在 `~/.illusion/channels.json`（不挤在 settings.json 中）：

```json
{
  "feishu": {
    "enabled": true,
    "app_id": "cli_xxx",
    "app_secret": "your-secret",
    "domain": "feishu",
    "require_mention": true,
    "allow_bots": false,
    "group_sessions_per_user": true,
    "group_policy": {
      "mode": "open",
      "allowlist": [],
      "blacklist": [],
      "admin_list": []
    }
  }
}
```

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `enabled` | `false` | 是否启用该渠道 |
| `app_id` | — | 飞书应用 App ID |
| `app_secret` | — | 飞书应用 App Secret（明文） |
| `domain` | `"feishu"` | `"feishu"`（国内）或 `"lark"`（国际） |
| `require_mention` | `true` | 群组中是否要求 @机器人才响应 |
| `allow_bots` | `false` | 是否处理其他机器人的消息 |
| `group_sessions_per_user` | `true` | 群组会话是否按用户隔离 |
| `group_policy.mode` | `"open"` | `"open"` / `"disabled"` / `"allowlist"` / `"blacklist"` |
| `group_policy.allowlist` | `[]` | 允许的 chat_id 列表（mode=allowlist 时生效） |
| `group_policy.blacklist` | `[]` | 拒绝的 chat_id 列表（mode=blacklist 时生效） |
| `group_policy.admin_list` | `[]` | 永远放行的 user_id 列表（管理员） |

### 飞书侧斜杠命令

可以直接在飞书会话中管理会话：

| 命令 | 说明 |
|------|------|
| `/help` | 显示可用命令 |
| `/clear` | 清空当前飞书会话历史 |
| `/new` | 开启新的飞书会话 |
| `/sessions` | 列出本地终端会话（未完成的工作） |
| `/resume [id\|序号]` | 恢复本地终端会话到飞书 |
| `/detach` | 将当前飞书会话保存为本地终端会话 |
| `/model [show\|set 名称]` | 查看或切换会话模型 |

**远程继续工作流程：**
1. 在终端开始一个编码任务，中途退出
2. 在飞书发送 `/sessions` —— 看到未完成的终端会话
3. 发送 `/resume 1` —— 把会话拉到飞书，继续工作
4. 发送 `/detach` —— 保存回本地，用 `illusion --resume <id>` 在终端继续

### 飞书内置工具

启用飞书渠道后，agent 自动获得飞书专属工具：

| 工具 | 说明 |
|------|------|
| `feishu_doc_read` | 读取飞书 Docx/Wiki 文档为纯文本 |
| `feishu_doc_create` | 创建新的飞书 Docx 文档 |
| `feishu_drive_list` | 列出飞书云盘文件夹下的文件 |
| `feishu_drive_upload` | 上传本地文件到飞书云盘 |
| `feishu_drive_download` | 下载飞书云盘文件到本地 |

这些工具使用相同的 App 凭据，agent 可自主调用。

### 权限交互

所有渠道会话默认以**自动模式**运行——工具调用自动批准，无需用户确认。这与终端界面不同，终端默认权限模式下修改类工具需要确认。

自动模式适用于渠道会话中的所有工具（bash、文件写入、编辑等），无需手动审批。

> **注意**：`ask_user` 提问和计划审批仍需用户输入——这些是交互式提示，不是权限检查。

### 常见问题排查

| 问题 | 解决方案 |
|------|----------|
| 飞书无响应 | 查看 `~/.illusion/channels/serve.log` 日志 |
| 守护进程未自动启动 | 运行 `illusion channel status` 检查；手动运行 `illusion channel serve` 查看日志 |
| 日志中出现 `processor not found` | 无害——这是已读回执事件，已用空处理器处理 |
| 卡片不渲染表格 | 确保飞书客户端版本 ≥ 7.20（JSON 2.0 卡片需要） |
| WS 连接反复重连 | 检查 App ID/Secret 是否正确；确认事件订阅设为长连接模式 |
| 编辑次数超限（230072） | 不适用——卡片使用 `message.patch`，无编辑次数限制 |

### 快速开始（微信）

微信使用 **iLink Bot API**（腾讯官方 Bot API，通过 HTTPS 长轮询）。不是逆向 hook，不需要微信客户端运行。

#### 1. 配置渠道

```bash
illusion channel login
# 选择：2. 微信 / WeChat
```

这将：
1. 自动安装 `aiohttp`、`cryptography`、`qrcode`（仅首次）
2. 在浏览器中打开二维码页面
3. 用微信扫码授权 bot 身份
4. 保存凭据到 `~/.illusion/channels.json`

#### 2. 开始使用

```bash
illusion                    # 自动后台激活微信守护进程
# 或
illusion channel serve      # 前台模式（查看日志）
```

在微信给 bot 发消息——你会看到「对方正在输入」指示，然后收到完整回复。

#### 3. 关键限制

- **仅私聊**——bot 身份无法加入普通微信群
- **不支持消息编辑**——回复作为完整文本发送（打字状态指示处理中）
- **2000 字符限制**——超长回复自动分多条发送，间隔 1.5s
- **会话过期**——如果看到 `errcode=-14`，重新运行 `illusion channel login` 扫码

### 快速开始（QQ）

QQ 使用**官方 QQ Bot API v2**（WebSocket 网关 + REST API）。需要在 QQ 开放平台注册机器人应用。

#### 1. 注册 QQ 机器人

1. 访问 [QQ 开放平台](https://q.qq.com)
2. 注册机器人应用，获取 **App ID** 和 **Client Secret**
3. 在机器人设置中开启 **C2C 私聊** 和 **群聊 @消息** 能力

#### 2. 配置渠道

```bash
illusion channel login
# 选择：3. QQ
```

这将：
1. 自动安装 `aiohttp`（仅首次）
2. 引导输入 App ID 和 Client Secret
3. 配置群组策略选项
4. 保存凭据到 `~/.illusion/channels.json`

#### 3. 开始使用

```bash
illusion                    # 自动后台激活 QQ 守护进程
# 或
illusion channel serve      # 前台模式（查看日志）
```

在 QQ 给机器人发消息——私聊直接回复，群聊需 @机器人。

#### 4. 关键限制

- **群聊需 @机器人**——群消息默认需要 @机器人 才响应（可配置）
- **不支持消息编辑**——回复作为完整文本发送
- **4000 字符限制**——超长回复自动分多条发送，间隔 1.5s
- **文件发送**——支持三步分片上传

### 渠道架构

```
src/illusion/channels/
├── __init__.py          # ChannelRunner（消息→agent 粘合层）+ maybe_spawn_channel_daemon
├── base.py              # Channel 抽象基类 + InboundMessage + 打字状态方法
├── base_commands.py     # BaseCommandHandler（通用斜杠命令基类）
├── config.py            # ChannelsConfig / FeishuChannelConfig / WeixinChannelConfig
├── serve.py             # 'illusion channel serve' 入口（多渠道调度）
├── pid.py               # PID 文件管理（避免重复启动守护进程）
├── feishu/
│   ├── adapter.py       # FeishuChannel：WS 连接、事件分发、准入控制
│   ├── ws_client.py     # lark-oapi WS 客户端包装
│   ├── messaging.py     # 卡片发送/更新、消息渲染
│   ├── stream_editor.py # 流式卡片编辑器（节流 patch 更新）
│   ├── session_map.py   # 飞书会话存储（chat_id → 会话）
│   └── commands.py      # FeishuCommandHandler（继承 BaseCommandHandler）
├── weixin/
│   ├── __init__.py      # WEIXIN_DEPENDENCIES / ensure_weixin_dependencies
│   ├── adapter.py       # WeixinChannel：长轮询、准入、context_token、打字状态
│   ├── ilink_api.py     # iLink Bot API 客户端（扫码/收发/打字/分片）
│   ├── session_map.py   # WeixinSessionStore（user_id → 会话）
│   └── commands.py      # WeixinCommandHandler（继承 BaseCommandHandler）
├── qq/
│   ├── __init__.py      # QQ_DEPENDENCIES / ensure_qq_dependencies
│   ├── adapter.py       # QQChannel：WS 连接、准入、消息标准化
│   ├── ws_client.py     # QQ Bot WS 网关客户端（心跳/重连/事件分发）
│   ├── api.py           # QQ Bot REST API 客户端（token/收发/上传）
│   ├── session_map.py   # QQSessionStore（chat_id → 会话）
│   └── commands.py      # QQCommandHandler（继承 BaseCommandHandler）
└── tools/
    ├── feishu_doc.py    # feishu_doc_read / feishu_doc_create
    └── feishu_drive.py  # feishu_drive_list / upload / download
```
