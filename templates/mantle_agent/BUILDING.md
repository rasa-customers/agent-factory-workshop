# Building a Mantle agent in this workspace

This folder is a Mantle project. Run every `rasa` command from here.

- `agent.yml` — identity, persona, global `rules`. Keep `orchestrator.model_group: main_model`.
- `integrations.yml` — already wired: the model goes through the workshop proxy, and the
  **travel MCP server** is declared as `travel`. **Do not change model settings.**
- `skills/<skill_id>/skill.md` — one folder per skill. Frontmatter `name`, `description`
  (when to activate), optional `import_tools`, then prose instructions.
- `skills/<skill_id>/memory.yml` — values the skill remembers (`schema: public: <field>: {type, llm_settable, description}`).
- Delete `skills/placeholder/` once you have a real skill (a project needs at least one skill).

## Using the travel tools
Import them in a skill's frontmatter:

```yaml
import_tools:
  - mcp/travel:get_flight
  - mcp/travel:get_weather
  - mcp/travel:get_meeting
  - mcp/travel:estimate_travel_minutes
  - mcp/travel:update_dashboard
  # when the brief asks for them:
  - mcp/travel:find_alternate_flights
  - mcp/travel:available_meeting_times
  - mcp/travel:reschedule_meeting
```

**One skill per job.** A skill that checks the trip, one that finds an alternate flight, one that moves the
meeting: each gets its own folder and a `description` that says when it applies. Rules for several skills:

- **What every reply must do goes in `agent.yml` `rules`**, not in one skill: the dashboard link in the first
  reply, keeping the dashboard in sync, the verdict format, never inventing facts. A rule that lives in one
  skill is forgotten the moment another skill is active.
- **Any skill that states a verdict or new facts updates the dashboard**, so it imports `update_dashboard`
  and `estimate_travel_minutes` along with the tools it needs to look things up.
- **The trip check answers first.** A new skill (alternate flights, moving the meeting) activates when the
  traveller asks for it or accepts an offer, never on the first message. The trip-check skill can offer it
  ("Want me to look for an earlier flight?").
- Skills share facts through the tools (call `get_flight` again rather than remembering it).
- When you add a skill, delete `skills/placeholder/` if it is still there.

What each tool does (they already know the traveller — **never ask the user for flight or meeting details**):

| Tool | Arguments | Returns |
|---|---|---|
| `get_flight` | none needed | the traveller's booked flight: `flight_number`, `airline`, `origin`, `destination`, `status`, `delay_minutes`, `gate`, `previous_gate`, `terminal`, `scheduled_arrival`, `estimated_arrival` (ISO times) |
| `get_meeting` | none | `title`, `start` (ISO time), `address` |
| `get_weather` | `location` (e.g. "New York"), `at` (ISO time, e.g. the flight's `estimated_arrival`) | `temperature_c`, `condition`, wind/precipitation |
| `estimate_travel_minutes` | `origin` ("JFK", "LGA" or "EWR"), `destination_address`, `depart_at` (ISO), `mode`: `"car"` or `"subway"` only | `minutes`, `arrives_at` (ISO clock time you'd get there), `note`, `from`/`to` (name, lat, lon) |
| `find_alternate_flights` | none | `flights`: other flights today with `flight_number`, `airline`, `arrival_airport`, `departs`, `estimated_arrival`, `seats_left` |
| `available_meeting_times` | none | `slots`: later ISO start times the meeting can move to, and `current_start` |
| `reschedule_meeting` | `start`: one of the slots | `{ok, meeting}`. Only call it after the traveller says yes to that time. |
| `update_dashboard` | `panel`: `flight` \| `weather` \| `meeting` \| `verdict` \| `route`; `data`: a JSON object | `{ok, dashboard_url}`: the link the traveller opens |

The dashboard shows whatever keys you put in `data`. Share `dashboard_url` with the traveller as a Markdown link,
`[Open your dashboard](...)` (the chat turns the first Markdown link in a message into a button). For `verdict` ALWAYS send exactly `{status: yes|tight|no, slack_minutes, reason}` (`reason` = one plain sentence),
every time, including after a follow-up changes it. Replies to the traveller are plain sentences: never
show raw JSON, tool payloads or panel data in the chat; the dashboard is where data goes.

Tip: leave the airport 15 minutes after `estimated_arrival` (pass that as `depart_at`), then compare
`arrives_at` with the meeting `start` — no clock arithmetic needed beyond that. The same works for an
alternate flight (use its `arrival_airport` as `origin`) and for a new meeting slot.

After `estimate_travel_minutes`, send the `route` panel: `{from, to, mode, minutes}` straight from its result
(the dashboard can draw it on a map). After a reschedule or a chosen alternate, update `meeting` or
`flight`, `verdict` and `route` so the dashboard matches what you told the traveller.

## Validate, train, and try it
Call `train_project` — it validates and trains. Fix every error it reports and call it again until it says OK.
Only use frontmatter keys the Mantle docs list — there is no `id` key (the folder name is the skill id).

## Reference
The full Mantle documentation is in `.rasa/docs/mantle/` — start with `llms.txt` (an index), and search
`llms-full.txt` with `grep -n` for details (e.g. `grep -n "import_tools" .rasa/docs/mantle/llms-full.txt`).
