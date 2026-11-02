Build a conversational travel agent that helps someone who is flying to New York work out whether they'll
make their meeting — and keeps their dashboard in sync with the conversation.

The opening line will be something like: "I'm flying to New York. Check my flight, show me the weather when
I land, and help me work out whether I'll make my meeting."

What it should do:

- Look up the flight (get_flight), the weather at the destination for the estimated arrival time
  (get_weather), and the meeting (get_meeting).
- Work out the verdict: estimated arrival + 15 minutes to get off the plane + travel time to the meeting
  address (estimate_travel_minutes, by car unless the traveller asks about the subway) compared with the
  meeting start. Say "yes" with the minutes of slack, "tight" if the slack is under 15 minutes, or "no" with
  how late they'd be.
- **Keep the dashboard in sync** with update_dashboard: the dashboard shows the same facts the agent has
  told the traveller — the flight on the `flight` panel, weather on `weather`, the meeting on `meeting`,
  and the verdict on `verdict` (`status`: yes/tight/no, `slack_minutes` — negative if late — and a
  one-line `reason`). When an answer changes (say, the verdict after switching to the subway), the panel
  is updated too, so the verdict panel always matches the latest verdict in the chat. Travel time has no
  panel of its own; it shows up in the verdict's reason.
- **Link to the dashboard.** Its first reply includes a Markdown link to the traveller's dashboard,
  `[Open your dashboard](...)`.
- Handle follow-ups and keep both the conversation and the dashboard up to date, e.g. "What if I take the
  subway instead?" (recompute with subway travel time and update the verdict), "Is it going to rain when I
  land?", "Has my gate changed?".
- Be brief and conversational — two or three sentences per reply. Never invent flight, weather or meeting
  details — they all come from the tools (and never ask the traveller for them). Anything the tools return
  (including the travel note) is fair to mention; don't add claims of its own.

All the tools come from the travel MCP server (`mcp/travel:...`).
