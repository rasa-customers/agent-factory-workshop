## What the factory always includes

These parts are fixed whatever the brief says: they are what makes the agent trustworthy and keeps the
dashboard from Breakout 1 in sync.

- **Tools.** All the tools come from the travel MCP server (`mcp/travel:...`): get_flight,
  get_weather, get_meeting, estimate_travel_minutes and update_dashboard, plus find_alternate_flights,
  available_meeting_times and reschedule_meeting when the brief asks for them. It only reschedules the
  meeting after the traveller says yes to a specific time.
- **Facts come from the tools.** It looks up the flight (get_flight), the weather at the destination for
  the estimated arrival time (get_weather), and the meeting (get_meeting). It never invents flight,
  weather or meeting details and never asks the traveller for them. Anything the tools return (including
  the travel note) is fair to mention; it doesn't add claims of its own.
- **The verdict.** Estimated arrival + 15 minutes to get off the plane + travel time to the meeting
  address (estimate_travel_minutes, by car unless the traveller asks about the subway) compared with the
  meeting start. "yes" with the minutes of slack, "tight" if the slack is under 15 minutes, or "no" with
  how late they'd be.
- **Keep the dashboard in sync** with update_dashboard: the flight goes on the `flight` panel, weather on
  `weather`, the meeting on `meeting`, the verdict on `verdict`, and the trip from the airport to the
  meeting on `route` (from, to, mode and minutes, as estimate_travel_minutes returns them). The verdict is
  sent as `status` (yes/tight/no), `slack_minutes` (negative if late) and a one-line `reason` that
  includes the travel time. The dashboard and the chat never contradict each other; the dashboard may
  show details a short reply leaves out. When an answer changes (say, the verdict after switching to the
  subway), the panels are updated too, so the verdict panel always matches the latest verdict in the chat.
- **Link to the dashboard.** Its first reply includes a Markdown link to the traveller's dashboard,
  `[Open your dashboard](...)`.
- **Follow-ups.** It handles follow-ups and keeps both the conversation and the dashboard up to date,
  e.g. "What if I take the subway instead?" (recompute with subway travel time and update the verdict),
  "Is it going to rain when I land?", "Has my gate changed?".
