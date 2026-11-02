---
name: Explain The Check
description: >
  Explain what the independent checker found in a build: why it failed, what it tested, or what it saw.
  Activate when someone asks why a build failed, what went wrong, what the checker found, or how it was
  tested.
import_tools:
  - mcp/factory:build_result
---

Call build_result (add `job_id` only if they named a specific build). Its `check_report` lists every
expectation the checker derived from the spec, with the evidence it saw and whether it passed.

- If it failed: name the one or two failed expectations in plain words, say what the checker actually saw,
  and suggest the next step: ask for a change that fixes it, or, if they want to carry on, the command in
  the error.
- If it passed: say how many expectations it checked and give two or three examples of what it verified,
  so they see the checker never read the code and judged only what a user would see.

Keep it short. Quote the evidence; never guess beyond it.
