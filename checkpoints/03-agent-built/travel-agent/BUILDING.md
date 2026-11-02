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
```

What each tool does (they already know the traveller — **never ask the user for flight or meeting details**):

| Tool | Arguments | Returns |
|---|---|---|
| `get_flight` | none needed | the traveller's booked flight: `flight_number`, `airline`, `origin`, `destination`, `status`, `delay_minutes`, `gate`, `previous_gate`, `terminal`, `scheduled_arrival`, `estimated_arrival` (ISO times) |
| `get_meeting` | none | `title`, `start` (ISO time), `address` |
| `get_weather` | `location` (e.g. "New York"), `at` (ISO time, e.g. the flight's `estimated_arrival`) | `temperature_c`, `condition`, wind/precipitation |
| `estimate_travel_minutes` | `origin` (e.g. "JFK"), `destination_address`, `depart_at` (ISO), `mode`: `"car"` or `"subway"` only | `minutes`, `arrives_at` (ISO clock time you'd get there), `note` |
| `update_dashboard` | `panel`: `flight` \| `weather` \| `meeting` \| `verdict`; `data`: a JSON object | `{ok, dashboard_url}`: the link the traveller opens |

The dashboard shows whatever keys you put in `data`. Share `dashboard_url` with the traveller as a Markdown link,
`[Open your dashboard](...)` (the chat turns the first Markdown link in a message into a button). For `verdict` use `{status: yes|tight|no, slack_minutes, reason}`.

Tip: leave the airport 15 minutes after `estimated_arrival` (pass that as `depart_at`), then compare
`arrives_at` with the meeting `start` — no clock arithmetic needed beyond that.

## Validate, train, and try it
Call `train_project` — it validates and trains. Fix every error it reports and call it again until it says OK.
Only use frontmatter keys the Mantle docs list — there is no `id` key (the folder name is the skill id).

## Reference
The full Mantle documentation is in `.rasa/docs/mantle/` — start with `llms.txt` (an index), and search
`llms-full.txt` with `grep -n` for details (e.g. `grep -n "import_tools" .rasa/docs/mantle/llms-full.txt`).
