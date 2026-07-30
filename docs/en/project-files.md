# Project Instruction & Memory Files

## AI Instruction Files (CLAUDE.md / ILLUSION.md / AGENTS.md)

`CLAUDE.md`, `ILLUSION.md`, and `AGENTS.md` are **equivalent** AI instruction files. IllusionAgent recognizes all three names interchangeably.

### Discovery Locations

The system scans for these files in the following locations (within the current working directory only, **not** in `~/.illusion/`):

1. **Project root**: `{cwd}/CLAUDE.md`, `{cwd}/AGENTS.md`, `{cwd}/ILLUSION.md`
2. **`.claude/` directory**: `{cwd}/.claude/CLAUDE.md`
3. **`.illusion/` directory**: `{cwd}/.illusion/CLAUDE.md`, `{cwd}/.illusion/AGENTS.md`, `{cwd}/.illusion/ILLUSION.md`

All discovered files are merged into a single `# Project Instructions` section in the system prompt. Each file is limited to 12,000 characters (truncated if exceeded).

### Rules Files

In addition to the instruction files above, the system also scans:

- `{cwd}/.claude/rules/*.md` — sorted by filename, each file is an independent rule

### Usage

Create any of these files in your project root to provide project-specific context and instructions:

```markdown
# Project Description

This is a Python Web project using the FastAPI framework.

## Code Standards

- Use Python 3.10+ features
- Follow PEP 8 code style
- Use type hints

## Directory Structure

- src/api: API routes
- src/models: Data models
- src/services: Business logic

## Notes

- Do not modify files in the tests/ directory
- Run pytest before committing
```

### Source Reference

File discovery logic: `src/illusion/prompts/claudemd.py` — `discover_claude_md_files()` function.

---

## Memory Files (MEMORY.md)

The memory system provides project knowledge persistence through `MEMORY.md` and associated memory files.

### Storage Locations

Memory files are stored in two locations, with the project-level location taking priority:

1. **Project-level** (priority): `{cwd}/.illusion/memory/`
2. **Global fallback**: `~/.illusion/memory/{project_name}-{sha1_hash_prefix}/`

The directory name format for global fallback is `{path.name}-{sha1(path)[:12]}`, located under `~/.illusion/memory/` (symmetric with the project-level `{cwd}/.illusion/memory/`).

### MEMORY.md Entry File

`MEMORY.md` is the entry point file that serves as an index. Each entry is a one-line pointer:

```markdown
- [Title](filename.md) — one-line description
- [Another Topic](another-file.md) — another description
```

**Limits:**
- Maximum 200 lines (controlled by `memory.max_entrypoint_lines` in settings.json)
- Maximum 5 memory files (controlled by `memory.max_files` in settings.json)

### Memory File Format

Each memory file uses frontmatter format:

```markdown
---
name: short-kebab-case-slug
description: One-line summary for relevance matching
metadata:
  type: user|feedback|project|reference
---

Content of the memory entry.
```

### Memory Types

| Type | Purpose |
|------|---------|
| `user` | User role, goals, preferences, knowledge level |
| `feedback` | Guidance on how to approach work (corrections and confirmations) |
| `project` | Ongoing work, goals, initiatives, bugs, incidents |
| `reference` | Pointers to external systems (Linear, Slack, Grafana, etc.) |

### Memory Management

Memory entries can be managed through:
- The `/memory` slash command in interactive sessions
- The `remember` skill
- Direct file editing in the memory directory

### Initialization

The `/init` command creates an initial `MEMORY.md` template at `{cwd}/.illusion/memory/MEMORY.md`.

### Source Reference

- Path resolution: `src/illusion/memory/paths.py`
- Loading logic: `src/illusion/memory/memdir.py`
- Management: `src/illusion/memory/manager.py`
