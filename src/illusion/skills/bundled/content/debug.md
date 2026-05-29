---
name: debug
description: Enable debug logging for this session and help diagnose issues
---

# Debug Skill

Help the user debug an issue they're encountering in this current Illusion Code session.

## Session Debug Log

The debug log for the current session is located at the path shown in the session startup output.

## Issue Description

The user's issue description will be provided as arguments. If no description is given, read the debug log and summarize any errors, warnings, or notable issues.

## Settings

Remember that settings are in:
* user - ~/.illusion/settings.json
* project - .illusion/settings.json

## Instructions

1. Review the user's issue description
2. Look for [ERROR] and [WARN] entries, stack traces, and failure patterns in the debug log
3. Consider launching a subagent to understand the relevant Illusion Code features
4. Explain what you found in plain language
5. Suggest concrete fixes or next steps

## Rules

- Read the error message carefully before searching code
- Don't guess — verify your hypothesis before changing code
- Fix the root cause, not the symptom
- Don't retry the same approach if it failed — investigate why
- If stuck after 3 attempts, explain what you've tried and ask for help
