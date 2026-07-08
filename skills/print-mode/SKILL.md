---
name: print-mode
description: Complete agent-facing guide for installing, authenticating, and driving Illusion Code's non-interactive print mode (-p) for automation and programmatic control. Invoke when an agent needs to install, configure, or operate Illusion Code as a subprocess for coding tasks.
---

# Illusion Code Print Mode: Agent Integration Guide

This skill teaches another agent how to install, authenticate, and operate Illusion Code's non-interactive print mode (`-p`) as a subprocess for coding tasks. Print mode is the integration point for programmatic control: submit a prompt, stream the response, exit.

> **Live documentation**: Always fetch the latest docs from the GitHub repository before acting — do not rely on hardcoded instructions in this skill, as the project evolves. Repo: `https://github.com/YunTaiHua/illusion-code`. Docs directory: `https://github.com/YunTaiHua/illusion-code/tree/main/docs`.

## Phase 0: Fetch Current Documentation (MANDATORY before install)

Before installing or configuring, use a web fetch tool (`WebFetch`, `web_fetch`, or equivalent) to read the latest docs. This skill only outlines the workflow — concrete flags, file paths, and auth providers may have changed.

Recommended fetch order:

1. **README** — `https://github.com/YunTaiHua/illusion-code` — project overview, install methods, latest version
2. **Getting Started** — `https://github.com/YunTaiHua/illusion-code/blob/main/docs/en/getting-started.md` — install steps, basic usage, requirements
3. **Command System** — `https://github.com/YunTaiHua/illusion-code/blob/main/docs/en/commands.md` — full CLI flag reference
4. **Settings** — `https://github.com/YunTaiHua/illusion-code/blob/main/docs/en/settings.md` — settings.json schema, credentials, auth providers
5. **Architecture** — `https://github.com/YunTaiHua/illusion-code/blob/main/docs/en/architecture.md` — only if you need deep internals

> If the repo URL above 404s, fall back to searching PyPI for the `illusion-code` package and follow its homepage link. Do NOT assume the install commands below are current — verify against the fetched docs.

## Phase 1: Installation

**Recommended (end users, no Node.js required)**:

```bash
pip install illusion-code
```

This installs the `illusion` command globally with pre-built frontends. Verify:

```bash
illusion --version
```

**From source (developers, requires Node.js 18+)**:

```bash
git clone https://github.com/YunTaiHua/illusion-code.git
cd illusion-code
pip install .          # standard install
# or
pip install -e .       # editable install (code changes take effect immediately)
```

> Always confirm the exact install command from the fetched Getting Started doc. The project also supports `uv sync` for development — see the docs for trade-offs.

## Phase 2: Authentication (Required Before First Run)

Illusion Code needs API credentials. Without auth, runs exit with an error code.

```bash
illusion auth login
```

This launches an interactive provider picker. **This step is interactive** — it is the one operation that cannot be done in print mode. Complete it once, manually or via a TTY-capable subprocess, before any `-p` invocation.

Common providers (verify against fetched Settings doc):

- **Custom** — API format (anthropic/openai), base URL, API key, model name
- **Anthropic** — direct API key
- **OpenAI** — direct API key
- **GitHub Copilot** — OAuth device flow
- **OpenAI Codex** — OAuth device flow

Credentials are stored in `~/.illusion/credentials.json` (or `%USERPROFILE%\.illusion\credentials.json` on Windows), grouped by `env_N`. The `settings.json` `env_N` blocks reference model names like `env_1.model_2`.

> **Verify the provider list and credential file path from the fetched Settings doc** — new providers may have been added.

## Phase 3: Verify the Environment

After install + auth, confirm the environment is usable before scripting:

```bash
# List configured environments/models (check fetched commands.md for the exact flag)
illusion auth status      # or equivalent — verify against docs
illusion -p "Reply with: OK" --output-format json
```

The second command should print `{"type": "result", "text": "OK"}` and exit with code 0. If it exits non-zero, check:

- `~/.illusion/credentials.json` exists and has an `env_N` entry
- `~/.illusion/settings.json` has a valid `env_N` block with `model_N` names
- API key is valid (run `illusion auth login` again if expired)

## Phase 4: Print Mode Core (The Integration Point)

Print mode is the only fully non-interactive execution path. Every `-p` invocation is an atomic request-response.

### Basic invocation

```bash
illusion -p "<prompt>"
```

**Critical rule**: `-p`'s value (the prompt) **must be the last argument**. typer parses it greedily; placing flags after it causes parse errors.

### Exit codes (always check these)

| Code | Meaning | Agent action |
|------|---------|--------------|
| 0 | Normal completion | Parse stdout for the result |
| 1 | Error | Read stderr for the failure reason; fix and retry |
| 2 | Waiting for user answer | A question was raised — answer with `illusion -c -p "<answer>"` |

### stdout vs stderr

- **stdout**: assistant text deltas, JSON results (depending on `--output-format`)
- **stderr**: status messages, permission denials, questions, errors

For programmatic parsing, use `--output-format json` (single JSON object at end) or `--output-format stream-json` (one JSON object per line).

## Phase 5: Permission Modes (Critical for Autonomous Operation)

Print mode never prompts for permission interactively. Choose explicitly per task:

| Mode | Behavior | Use when |
|------|----------|----------|
| `default` (omit) | Mutating tools **directly denied**, message to stderr | Read-only analysis, research, code review |
| `full_auto` | All tools execute (writes, bash, edits) | Autonomous coding, file modification, running commands |
| `plan` | All mutation tools blocked | Planning only, no side effects |

```bash
# Read-only — safe, no side effects
illusion -p "Analyze the project structure and list TODO comments"

# Autonomous coding — must be explicit
illusion --permission-mode full_auto -p "Fix the failing tests in tests/test_auth.py"
```

On denial, stderr shows: `⏸️ Permission denied: <tool> (<reason>). ... use --permission-mode full_auto to allow`. The denied tool call is recorded as a failed tool_result in the session, so the LLM adapts and tries an alternative approach.

> **Recommendation for autonomous agents**: default to `full_auto` for coding tasks. Use `default` only when you intentionally want a read-only safety net.

## Phase 6: ask_user_question — Cross-Turn Non-Interactive Pattern

When the LLM calls the `ask_user_question` tool, print mode does NOT block. Instead it persists the question and exits with code 2, expecting the controlling agent to answer in the next invocation.

### Two-turn flow

```bash
# Turn 1: prompt that triggers a question
illusion -p "Refactor auth.py"
# → exits with code 2, stderr prints the question with headers in brackets

# Turn 2: inject the answer and resume
illusion -c -p "<answer>"
# → resumes execution with the answer injected as tool_result
```

### Answer formats

| Scenario | Format | Example |
|----------|--------|---------|
| Single question | Plain text | `strawberry` |
| Single question (multiSelect) | Comma-separated | `strawberry,mango` |
| Multiple questions | JSON, keys = headers | `{"Fruit": "strawberry", "OS": "Windows"}` |
| Multiple questions (multiSelect) | JSON with arrays | `{"Fruit": ["strawberry", "mango"]}` |

Headers are shown in brackets in Turn 1's stderr output (e.g., `[Fruit] Which fruit do you like?`). Non-JSON input for multi-question is passed as-is to the LLM (backward compatible, but JSON is preferred for reliability).

### Shell escaping for JSON answers

In bash, escape the inner quotes:

```bash
illusion -c -p "{\"Fruit\": \"strawberry\", \"OS\": \"Windows\"}"
```

In PowerShell, the same escaping works. If your agent controls the subprocess via a library that passes args as a list (not a shell string), no escaping is needed — pass the raw JSON string as a single argv element.

### Detecting pending questions programmatically

1. Capture exit code; if `2`, a question is pending
2. Parse stderr for lines starting with `[<header>]` — these are the questions
3. Build the JSON answer from the headers detected
4. Resume with `illusion -c -p "<json>"`

## Phase 7: Session Continuity

Sessions persist to disk and can be resumed across invocations.

| Flag | Description |
|------|-------------|
| `-c` / `--continue` | Continue the most recent session in the current working directory |
| `-r <ID>` / `--resume <ID>` | Resume a specific session by ID |

Both require `-p`. Use `-c` for the linear "question → answer" flow; use `-r <ID>` when you need to juggle multiple parallel sessions (capture the session ID from the first run's output or session storage).

Session files live under `~/.illusion/sessions/` (verify path in fetched docs). The session ID is a short hex string (e.g., `abc123def456`).

## Phase 8: Persistent Parameters

These flags persist to `settings.json` and survive across sessions — set them once in a setup phase, then omit them:

| Flag | Description |
|------|-------------|
| `-m <env_N.model_N>` / `--model` | Model selection |
| `-e <LEVEL>` / `--effort` | Effort: `low` / `medium` / `high` / `max` |
| `-t <N>` / `--max-turns` | Max agentic turns |
| `--permission-mode <MODE>` | Permission mode |

Non-persistent (per-invocation only): `-c`, `-r`, `-n`, `--dangerously-skip-permissions`, `--output-format`.

> **Avoid `--dangerously-skip-permissions`** — prefer `--permission-mode full_auto` which expresses the same intent explicitly and persists.

## Phase 9: Output Formats

`--output-format <FORMAT>`:

| Format | Description | When to use |
|--------|-------------|-------------|
| `text` (default) | Plain text to stdout, status to stderr | Human reading, simple scripts |
| `json` | Single JSON object `{"type": "result", "text": "..."}` at end | Programmatic result parsing |
| `stream-json` | One JSON object per line (events: `assistant_delta`, `tool_started`, `tool_completed`, `assistant_complete`, `error`, `status`, `system`) | Real-time monitoring, progress tracking |

For autonomous agents, `stream-json` is recommended — you can track tool execution progress and detect errors mid-run without waiting for completion.

## Phase 10: Common Autonomous Workflows

### Workflow A: Read-only codebase analysis

```bash
illusion -p "Find all functions in src/auth/ that handle token refresh and summarize their approach" --output-format json
```

Exit code 0 → parse JSON result. No side effects.

### Workflow B: Autonomous bug fix

```bash
# Setup (one-time, persists)
illusion -m env_1.model_2 -e high --permission-mode full_auto -p "noop" || true

# Execute
illusion --permission-mode full_auto -p "The test test_login_expires in tests/test_auth.py is failing. Investigate and fix it."
```

### Workflow C: Multi-turn clarification flow

```bash
# Turn 1: task triggers a question
illusion -p "Add a rate limiter to the API"
# → exit 2, stderr: [Algorithm] Which algorithm? [Limit] What RPS?

# Turn 2: answer
illusion -c -p "{\"Algorithm\": \"token bucket\", \"Limit\": \"100\"}"
# → resumes, completes the implementation
```

### Workflow D: Parallel sessions

```bash
# Session A
illusion -p "Refactor the database layer" -n "db-refactor"
# Capture session ID from output/storage

# Session B (different task, different ID)
illusion -p "Add telemetry to the API" -n "telemetry"

# Resume A later
illusion -r <session-a-id> -p "Continue where you left off"
```

## Phase 11: Integration Checklist for Controlling Agents

Before driving Illusion Code autonomously, ensure:

1. **Installed** — `illusion --version` succeeds
2. **Authenticated** — `illusion auth login` completed; `~/.illusion/credentials.json` has a valid `env_N`
3. **Environment verified** — a trivial `-p "OK"` returns exit 0
4. **Docs fetched** — you have read the latest Getting Started, Commands, and Settings docs from the repo
5. **Permission strategy decided** — `default` for read-only, `full_auto` for coding
6. **Exit code handling** — your wrapper checks 0/1/2 and routes accordingly
7. **Answer format** — JSON builder ready for multi-question (exit 2) cases
8. **Session tracking** — you capture and reuse session IDs for multi-turn flows

## Anti-Patterns (Do NOT)

- **Don't** hardcode install/auth commands from this skill — always fetch the latest from the repo
- **Don't** expect interactive prompts in print mode — it never waits
- **Don't** put `-p`'s value before other flags — it must be last
- **Don't** forget `--permission-mode full_auto` for coding tasks — `default` will deny all writes
- **Don't** ignore exit code 2 — it means a question is pending and must be answered
- **Don't** use `--dangerously-skip-permissions` — prefer the explicit `--permission-mode full_auto`
- **Don't** assume provider names or file paths — verify against fetched Settings doc
- **Don't** run `illusion auth login` inside a print-mode loop — it is interactive and must be done once via TTY

## Reference URLs (verify they resolve before relying on them)

- Repository: `https://github.com/YunTaiHua/illusion-code`
- PyPI package: `https://pypi.org/project/illusion-code/`
- Getting Started: `https://github.com/YunTaiHua/illusion-code/blob/main/docs/en/getting-started.md`
- Commands: `https://github.com/YunTaiHua/illusion-code/blob/main/docs/en/commands.md`
- Settings: `https://github.com/YunTaiHua/illusion-code/blob/main/docs/en/settings.md`
- Architecture: `https://github.com/YunTaiHua/illusion-code/blob/main/docs/en/architecture.md`

If any URL above 404s, the docs may have been reorganized — start from the repository root and navigate to the `docs/` directory to find the current paths.
