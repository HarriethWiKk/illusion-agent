---
name: illusion-print-mode
description: Guide for using Illusion Code's non-interactive print mode (-p) for automation and agent control. Invoke when user asks about print mode, non-interactive usage, scripting illusion, or controlling illusion from another agent.
---

# Print Mode: Non-Interactive Automation

Print mode (`-p`) lets you run Illusion Code as a non-interactive command: submit a prompt, stream the response, then exit. Designed for scripts, CI, and controlling Illusion Code from other agents.

## Core Principle

**Print mode is fully non-interactive.** Every `-p` invocation is an atomic request-response — no waiting for interactive input within the same turn. This lets other agents control Illusion Code programmatically.

## Basic Usage

```bash
illusion -p "<prompt>"
```

- `-p` value (the prompt) **must be the last argument** — typer parses it greedily
- Streams response to stdout; status/errors go to stderr
- Exits with code 0 (success), 1 (error), or 2 (waiting for user answer)

## Permission Modes (Critical)

Print mode never prompts for permission. Choose explicitly:

| Mode | Behavior | Use When |
|------|----------|----------|
| `default` (omit) | Mutating tools **directly denied** | Read-only analysis, research |
| `full_auto` | All tools execute | Writing files, running commands |
| `plan` | All mutation tools blocked | Planning only |

```bash
# Read-only — safe, no side effects
illusion -p "Analyze the project structure"

# Allow writes/commands — must be explicit
illusion --permission-mode full_auto -p "Fix the failing tests"
```

If a tool is denied, stderr shows: `⏸️ Permission denied: <tool> (<reason>). ... use --permission-mode full_auto to allow`

## ask_user_question: Cross-Turn Non-Interactive Pattern

When the LLM calls `ask_user_question`, print mode does NOT block waiting for input. Instead:

1. **Turn 1**: `illusion -p "do something"` → LLM calls `ask_user_question` → question persisted to `pending-question-<session_id>.json` → program exits with **code 2**
2. **Turn 2**: `illusion -c -p "<answer>"` → detects pending question → injects answer → resumes execution

### Answer Formats

| Scenario | Format | Example |
|----------|--------|---------|
| Single question | Plain text | `strawberry` |
| Single question (multiSelect) | Comma-separated | `strawberry,mango` |
| Multiple questions | JSON, keys = headers | `{"Fruit": "strawberry", "OS": "Windows"}` |
| Multiple questions (multiSelect) | JSON with arrays | `{"Fruit": ["strawberry", "mango"]}` |

Headers are shown in brackets during Turn 1 output (e.g., `[Fruit] Which fruit?`). Non-JSON input for multi-question is passed as-is to the LLM (backward compatible).

```bash
# Single answer
illusion -c -p "strawberry"

# Multi-question JSON answer (escape quotes in shell)
illusion -c -p "{\"Fruit\": \"strawberry\", \"OS\": \"Windows\"}"
```

## Exit Codes

| Code | Meaning | Next Action |
|------|---------|-------------|
| 0 | Normal completion | Read stdout for result |
| 1 | Error | Check stderr for details |
| 2 | Waiting for user answer | Answer with `illusion -c -p "<answer>"` |

## Session Resume

| Flag | Description |
|------|-------------|
| `-c` / `--continue` | Continue most recent session in current directory |
| `-r <ID>` / `--resume <ID>` | Resume specific session by ID |

Both require `-p`. Combine with answer to continue after a pending question:

```bash
illusion -c -p "the answer"
illusion -r abc123 -p "the answer"
```

## Persistent Parameters

These persist to `settings.json` (survive across sessions):

| Flag | Description |
|------|-------------|
| `-m <env_N.model_N>` / `--model` | Model selection |
| `-e <LEVEL>` / `--effort` | Effort: `low`/`medium`/`high`/`max` |
| `-t <N>` / `--max-turns` | Max agentic turns |
| `--permission-mode <MODE>` | Permission mode |

Non-persistent: `-c`, `-r`, `-n`, `--dangerously-skip-permissions`

## Output Formats

`--output-format <FORMAT>`:

| Format | Description |
|--------|-------------|
| `text` (default) | Plain text to stdout, status to stderr |
| `json` | Single JSON object `{"type": "result", "text": "..."}` at end |
| `stream-json` | One JSON object per line (events: `assistant_delta`, `tool_started`, `tool_completed`, `assistant_complete`, `error`, `status`, `system`) |

## Common Patterns

### Read-only analysis (safe default)
```bash
illusion -p "Find all TODO comments in the codebase"
```

### Execute changes (explicit auto)
```bash
illusion --permission-mode full_auto -p "Run the test suite and fix failures"
```

### Structured output for programmatic consumption
```bash
illusion -p "List all public functions in src/" --output-format json
```

### Multi-turn agent conversation
```bash
# Turn 1: ask
illusion -p "Plan a refactor of auth.py"
# Returns exit code 2 with a question about approach

# Turn 2: answer
illusion -c -p "{\"Approach\": \"JWT\", \"Scope\": \"full\"}"
# Continues execution with the answer injected
```

### Combined flags
```bash
illusion -m env_1.model_2 -e high -t 20 --permission-mode full_auto -c -p "Complete this feature"
```

## Integration Tips for Controlling Agents

1. **Always check exit code**: 2 means a question is pending — you must answer it
2. **Parse stderr for questions**: Turn 1 prints questions to stderr with headers in brackets
3. **Use JSON output for parsing**: `--output-format json` gives clean structured result
4. **Prefer `full_auto` for autonomous tasks**: Avoids permission denials mid-execution
5. **Persist model/effort once**: Set `-m` and `-e` in an initial setup call, they persist
6. **Session ID continuity**: `-c` resumes the most recent session; `-r <ID>` for specific ones

## Anti-Patterns

- **Don't** expect interactive prompts — print mode never waits
- **Don't** put `-p` value before other flags — it must be last
- **Don't** forget `--permission-mode full_auto` when writes are needed
- **Don't** ignore exit code 2 — it means a question needs answering
- **Don't** use `--dangerously-skip-permissions` — prefer `--permission-mode full_auto` (explicit intent)
