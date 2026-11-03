---
name: Unsupported Request Handler
description: >
  Sends a decline when the user asks for something this factory cannot build. Activated by the engine's
  `cannot_help` tool, not by routing.
routing:
  engine_managed: true
---

:::ordered_block id=main
name: default_unsupported_request_handler
steps:
  - id: gate_request_type
    noop: true
    next:
      - if: "session.default_unsupported_request_handler.request_type == 'out_of_domain_out_of_scope'"
        then: decline_out_of_domain_out_of_scope
      - else: decline_in_domain_out_of_scope
  - id: decline_in_domain_out_of_scope
    action: utter_decline_in_domain_out_of_scope
    next: END
  - id: decline_out_of_domain_out_of_scope
    action: utter_decline_out_of_domain_out_of_scope
    next: END
:::
