# 桌面版

IllusionAgent 桌面版基于 Electron 封装 Web 端，内置 Python 与 Node.js 运行时，提供便携版分发，支持 Windows、macOS、Linux。

## 📦 下载与安装

### Windows

1. 下载 `IllusionAgent-<版本>-win-x64.zip`。
2. 解压到任意目录（如 `D:\Apps\IllusionAgent`）。
3. 双击 `IllusionAgent.exe` 启动。
4. 首次启动可能触发 SmartScreen 警告，点击"更多信息"→"仍要运行"。

无需安装，配置写入 `%USERPROFILE%\.illusion\`。如需迁移，复制整个解压目录即可。

### macOS

1. 下载 `IllusionAgent-<版本>-mac-arm64.dmg`（Apple Silicon，Intel Mac 暂未提供）。
2. 打开 dmg，将 `IllusionAgent.app` 拖到"应用程序"。
3. 首次运行需绕过 Gatekeeper（见下节）。

配置写入 `~/.illusion/`。

### Linux

1. 下载 `IllusionAgent-<版本>-linux-x64.AppImage`（x64，arm64 暂未提供）。
2. 添加可执行权限：`chmod +x IllusionAgent-<版本>-linux<arch>.AppImage`。
3. 双击或命令行运行。

配置写入 `~/.illusion/`。

## 🔓 macOS 绕过 Gatekeeper

由于 `.app` 未签名，macOS Gatekeeper 会阻止首次运行。两种方式任选其一：

**方式一：右键打开（推荐，图形界面）**

1. 在 Finder 中找到 `IllusionAgent.app`。
2. 按住 **Control** 键单击该 app（或右键单击）。
3. 选择"打开"。
4. 在弹窗中再次点击"打开"。

**方式二：终端命令（一次性放行）**

```bash
xattr -dr com.apple.quarantine /Applications/IllusionAgent.app
```

执行后该 app 不再被 Gatekeeper 拦截。仅对当前用户有效，不影响系统其他 app。

## 🪟 Windows 便携版说明

- **无需安装**：解压即用，不写注册表，不进 `Program Files`。
- **SmartScreen 警告**：未签名 exe 首次启动可能被拦截，按"更多信息"→"仍要运行"放行。
- **迁移**：复制整个目录到其他机器即可运行。
- **卸载**：删除解压目录即可。如需清理配置，删除 `%USERPROFILE%\.illusion\`。

## 🐧 Linux AppImage 说明

- **无需安装**：AppImage 为单文件便携格式，加可执行权限即可运行。
- **桌面集成**：如需在应用菜单显示，可使用 [AppImageLauncher](https://github.com/TheAssassin/AppImageLauncher) 或手动创建 `.desktop` 文件。
- **FUSE 依赖**：AppImage 运行需要 FUSE 支持。极少数最小化系统可能需安装：
  - Ubuntu/Debian：`sudo apt install libfuse2`
  - Fedora：`sudo dnf install fuse`
- **卸载**：删除 AppImage 文件即可。配置在 `~/.illusion/`。

## 🐍 内置 Python / Node.js 运行时

桌面版内置一份独立的 Python 与 Node.js 运行时，位于应用资源目录内，**不污染系统 PATH**。

### 检测逻辑

| 运行时 | 优先级 | 说明 |
|---|---|---|
| 用户自有 Python / Node | 优先 | `PATH` 中可解析到符合版本要求的 `python` / `node` 时，使用用户环境 |
| 内置 Python / Node | 兜底 | 用户环境缺失或版本不达标时，使用内置运行时 |

### 暴露给 LLM 工具调用

- **用户已有环境**：仅用内置 Python 启动后端，不向用户暴露内置运行时。
- **用户无环境**：内置 Python / Node 的 bin 目录被加到后端进程的 `PATH` 前面，LLM 的工具调用（如 bash 工具执行 `python xxx.py` / `node xxx.js`）能直接使用内置运行时。

## 📌 托盘行为

| 操作 | 行为 |
|---|---|
| 点击窗口关闭按钮（×） | 隐藏窗口到系统托盘，应用继续运行 |
| 托盘图标单击 | 显示/隐藏主窗口 |
| 托盘菜单 → 退出 | 真正退出：关闭守护进程、释放端口、退出应用 |
| macOS Cmd+Q | 同"退出" |
| 重复启动 | 聚焦到现有窗口，不启动新实例 |

## 🔄 更新

便携版采用**整包替换**更新：检测新版本 → 下载 → 退出应用后替换整个目录 → 重新启动。配置目录 `~/.illusion/` 跨版本保留。

## ⚠️ 注意事项

- **未签名**：三端均无代码签名，Windows 触发 SmartScreen，macOS 触发 Gatekeeper，Linux 无影响。
- **首次启动较慢**：内置运行时首次初始化需数秒。
- **macOS 便携**：macOS 无真正"便携版"概念，仅提供未签名 `.app`（dmg 分发）。
