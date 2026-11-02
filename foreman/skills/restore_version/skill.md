---
name: Restore A Version
description: >
  Put an earlier version of a build back live. Activate when someone asks to go back, undo a change, or
  use an earlier version of their dashboard or agent.
import_tools:
  - mcp/factory:list_builds
  - mcp/factory:restore_build
tool_constraints:
  - restore_build:
      on_success: utter_restore_links
---

Never write links or URLs: buttons are added after restore_build.

Call list_builds and find the version they mean: "undo" or "go back" means the newest passed build before
the latest one of that kind. If it is unclear which one, show the passed versions as short lines and ask.
Say which version you will put back in one sentence, then call restore_build with its job_id. Tell them
it takes a few seconds for a dashboard and roughly a minute for an agent, and that any further changes will
build on the restored version.
