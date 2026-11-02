---
name: Build History
description: >
  Show what the factory has built for this person and what each brief said. Activate when someone asks what
  they have built, for their versions or history, or to see the brief or spec behind a build.
import_tools:
  - mcp/factory:list_builds
  - mcp/factory:get_brief
---

To list builds, call list_builds and show the newest few as short lines: what it was, the kind, and whether
it passed or failed. Mention that any version that passed can be put back.

To show a brief, call get_brief (with `kind` when they say dashboard or agent) and show it as it is: the
title line, the bullets, and every change asked for since. Say the factory adds its fixed contract on top.
