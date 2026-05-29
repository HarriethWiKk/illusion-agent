---
name: stuck
description: Diagnose frozen/stuck/slow Illusion Code sessions on this machine and provide diagnostic report.
---

# /stuck — diagnose frozen/slow Illusion Code sessions

The user thinks another Illusion Code session on this machine is frozen, stuck, or very slow. Investigate and provide a diagnostic report.

## What to look for

Scan for other Illusion Code processes (excluding the current one). The command name is `illusion`.

Signs of a stuck session:
- **High CPU (≥90%) sustained** — likely an infinite loop. Sample twice, 1-2s apart, to confirm it's not a transient spike.
- **Process state `D` (uninterruptible sleep)** — often an I/O hang. The `state` column in `ps` output; first character matters (ignore modifiers like `+`, `s`, `<`).
- **Process state `T` (stopped)** — user probably hit Ctrl+Z by accident.
- **Process state `Z` (zombie)** — parent isn't reaping.
- **Very high RSS (≥4GB)** — possible memory leak making the session sluggish.
- **Stuck child process** — a hung `git`, `node`, or shell subprocess can freeze the parent. Check `pgrep -lP <pid>` for each session.

## Investigation steps

1. **List all Illusion Code processes** (macOS/Linux):
   ```
   ps -axo pid=,pcpu=,rss=,etime=,state=,comm=,command= | grep -E 'illusion' | grep -v grep
   ```
   Filter to rows where `comm` is `illusion` or command contains "illusion".

2. **For anything suspicious**, gather more context:
   - Child processes: `pgrep -lP <pid>`
   - If high CPU: sample again after 1-2s to confirm it's sustained
   - If a child looks hung (e.g., a git command), note its full command line with `ps -p <child_pid> -o command=`
   - Check the session's debug log if you can infer the session ID: `~/.illusion/logs/<session-id>.log` (the last few hundred lines often show what it was doing before hanging)

3. **Consider a stack dump** for a truly frozen process (advanced, optional):
   - macOS: `sample <pid> 3` gives a 3-second native stack sample
   - Linux: `kill -QUIT <pid>` sends a thread dump to stderr
   - This is big — only grab it if the process is clearly hung and you want to know *why*

## Report

Format the report as a structured diagnostic:

1. **Summary** — one short line: hostname, Illusion Code version, and a terse symptom (e.g. "session PID 12345 pegged at 100% CPU for 10min")
2. **Details** — the full diagnostic dump:
   - PID, CPU%, RSS, state, uptime, command line, child processes
   - Your diagnosis of what's likely wrong
   - Relevant debug log tail if you captured it

## Notes
- Don't kill or signal any processes — this is diagnostic only.
- If the user gave an argument (e.g., a specific PID or symptom), focus there first.
- If no processes are stuck, tell the user directly that everything looks healthy.
