# 快速开始

## 🚀 快速开始

### 环境要求

- Python >= 3.10
- 支持 Windows、macOS、Linux
- Windows 用户：自动查找 Git，无需手动配置 PATH
- Node.js 18+：仅从源码安装时需要；通过 `pip install illusion-code` 安装无需 Node.js 环境

### 安装

#### 推荐方式：从 PyPI 安装

最简单的安装方式，自动安装前端并注册 `illusion` 命令到全局 PATH。**无需 Node.js 环境**，前端资源已预构建并包含在包中。

```bash
pip install illusion-code
```

无需克隆仓库，所有内容已包含在包中。

#### 备选方式：从源码安装

克隆仓库后本地安装，hatch build hook 会自动构建前端。

```bash
git clone https://github.com/YunTaiHua/illusion-code.git
cd illusion-code
pip install .
```

需要 Node.js 18+（用于前端构建）。

#### 备选方式：pip install -e .（可编辑安装，从源码）

从源码进行可编辑安装。与 `pip install .` 相同，会触发 hatch build hook 自动构建前端并全局注册 `illusion` 命令；与 `uv sync` 相同，源码修改立即生效，无需重新安装。

```bash
git clone https://github.com/YunTaiHua/illusion-code.git
cd illusion-code
pip install -e .
```

需要 Node.js 18+（用于前端构建）。

> **适用场景**：适合希望同时拥有可编辑安装（代码即时生效）和全局 `illusion` 命令的开发者。与 `uv sync` 不同，无需手动构建前端，也无需使用 `uv run` 包装。

#### 开发方式：uv sync（适合开发者）

`uv sync` 创建 editable install，不会触发 hatch build hook，需要手动构建前端。适合需要修改源代码的开发者。

```bash
git clone https://github.com/your-repo/illusion-code.git
cd illusion-code
uv sync

# 手动构建前端（uv sync 后必须执行）
python scripts/build_frontend.py              # 构建两者
python scripts/build_frontend.py --terminal   # 只构建终端 TUI
python scripts/build_frontend.py --web        # 只构建 Web UI
```

> **注意**：`uv sync` 不会将 `illusion` 命令注册到全局 PATH。使用方式：
>
> ```bash
> # 方式一：在项目目录下使用 uv run
> cd illusion-code
> uv run illusion
>
> # 方式二：激活虚拟环境
> # Windows
> .venv\Scripts\activate
> # macOS / Linux
> source .venv/bin/activate
> illusion
>
> # 方式三：使用 pip 全局安装（推荐）
> pip install .
>
> # 方式四：pip 可编辑安装（全局 + 代码即时生效）
> pip install -e .
> ```

#### 手动构建前端（仅源码安装需要）

如从源码安装后需要重新构建前端（例如更新了前端代码）。PyPI 用户无需此步骤。

**构建脚本（推荐）**

```bash
python scripts/build_frontend.py              # 构建两者
python scripts/build_frontend.py --terminal   # 只构建终端 TUI
python scripts/build_frontend.py --web        # 只构建 Web UI
```

**手动使用 npm**

```bash
# 终端 TUI（esbuild → dist/index.mjs）
cd frontend/terminal
npm install --no-fund --no-audit
npm run build
cd ../..

# Web UI（Vite → dist/）
cd frontend/web
npm install --no-fund --no-audit
npm run build
cd ../..
```

#### 四种方式对比

| | `pip install illusion-code` | `pip install .` | `pip install -e .` | `uv sync` |
|---|---|---|---|---|
| 来源 | PyPI | 本地 git clone | 本地 git clone | 本地 git clone |
| 前端构建 | 预构建（已包含） | 自动（hatch hook） | 自动（hatch hook） | 手动 |
| Node.js 要求 | **不需要** | 需要 18+ | 需要 18+ | 需要 18+ |
| `illusion` 命令 | 全局可用 | 全局可用 | 全局可用 | 仅项目内（需 `uv run` 或激活虚拟环境） |
| 安装类型 | 标准安装 | 标准安装 | 可编辑安装 | 可编辑安装 |
| 代码修改生效 | 需重新安装 | 需重新安装 | 即时生效 | 即时生效 |
| 适用场景 | 终端用户 | 贡献者 | 开发者（全局+可编辑） | 开发者 |

### 基本使用

> **首次使用建议**：先执行 `illusion auth login` 配置 API 认证，否则可能因未登录或模型不可用而报错退出。

```bash
# 首次使用：配置认证
illusion auth login

# 启动交互式会话（推荐）
illusion

# 启动 Web UI 浏览器界面
illusion web

# 自定义端口启动 Web UI
illusion web --port 8080

# 非交互式打印模式
illusion -p "帮我分析这个项目的结构"

# 指定模型
illusion -m env_1.model_2

# 继续最近会话（配合 -p 使用）
illusion -c -p "继续上次会话"

# 恢复指定会话（配合 -p 使用）
illusion -r <session-id> -p "继续"

# 设置权限模式
illusion --permission-mode full_auto

# 设置推理强度（持久化到 settings）
illusion -e high
```

> **注意**：终端界面（`illusion`）为推荐的首选模式。Web UI（`illusion web`）仅作为终端不可用时的补充方案。

---

## 🧪 开发与测试

```bash
# 安装开发依赖
uv sync --dev

# 运行测试
pytest
```

---

## 📄 许可证

本项目采用 [MIT](../LICENSE) 许可证开源。

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！
