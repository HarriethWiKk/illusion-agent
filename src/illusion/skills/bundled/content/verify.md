---
name: verify
description: Verify that a code change actually does what it's supposed to by running the app and observing behavior. Use when asked to verify a PR, confirm a fix works, test a change manually, check that a feature works, or validate local changes before pushing.
---

# Verify: Manual Feature Verification

Verify that a code change actually does what it's supposed to by running the app and observing behavior.

## When to use

Use this skill when:
- Asked to verify a PR or confirm a fix works
- Testing a change manually before pushing
- Checking that a feature works as expected
- Validating local changes

## Workflow

### 1. Understand the Change

Run `git diff` (or `git diff HEAD` if there are staged changes) to see what changed. If there are no git changes, review the most recently modified files.

Identify:
- What feature/fix was implemented
- What the expected behavior should be
- How to trigger/test the behavior

### 2. Determine Verification Method

Based on the change type, choose the appropriate verification:

**UI Changes:**
- Start the dev server
- Navigate to the affected page/component
- Interact with the changed elements
- Screenshot the result

**API Changes:**
- Start the server
- Use curl or similar to hit the affected endpoints
- Verify response codes and data

**CLI Changes:**
- Run the CLI with relevant flags/arguments
- Check output matches expectations

**Logic Changes:**
- Write a simple test script if needed
- Run with specific inputs
- Verify outputs

### 3. Execute Verification

1. **Setup**: Start any required services (dev server, database, etc.)
2. **Test the happy path**: The primary use case should work
3. **Test edge cases**: Boundary conditions, error cases
4. **Check for regressions**: Existing features still work

### 4. Report Results

Provide a clear report:
- What was tested
- What passed
- What failed (if anything)
- Screenshots/logs if relevant

## Rules

- Actually run the code, don't just read it
- Test the specific change, not the entire application
- Report honestly — if something doesn't work, say so
- Include reproduction steps for any failures
- If verification requires setup the user hasn't done, ask first
