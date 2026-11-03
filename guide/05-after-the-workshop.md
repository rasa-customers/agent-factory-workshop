# 5. After the workshop

Your workshop key stops working after the event. Everything else is yours.

## Use your own OpenAI key

Edit `.env`:

```bash
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1
RASA_LICENSE=...
FACTORY_MODEL=gpt-5.2   # every agent here uses this model; change it if you like
```

Then `uv run workshop doctor` and `uv run workshop up`. A dashboard build costs cents; a travel-agent
build somewhat more.

## Build something else

The factory builds two kinds of thing: a **dashboard** (a live web page fed by `POST /api/state`) and a
**Mantle agent** (skills that use MCP tools). To build something new, describe it to the foreman
and agree a brief, or write one yourself (start from `prompts/`). Be concrete about what someone would
*see*: the checker can only check what it can observe.

To go further:

| Change | Where |
|---|---|
| Give built agents new tools | Add `@mcp.tool()` functions to `travel_mcp/server.py`, and list them in `templates/mantle_agent/BUILDING.md` |
| Change what every build starts from | `templates/dashboard/`, `templates/mantle_agent/` |
| Change how the builder or checker think | `factory/agents.py` (their instructions) |
| Change the loop (rounds, what gets fed back) | `factory/pipeline.py` |
| Change what every brief must include | `factory/contracts/` |
| Teach the foreman new requests | `foreman/skills/` — then `rasa train` in `foreman/` |
| Test the foreman | Scenarios in `foreman/eval/scenarios/`, then `uv run workshop eval foreman` (these start real builds) |
| Test a built agent | Scenarios in `workspace/latest-agent/eval/scenarios/`, then `uv run workshop eval agent` |

## Checkpoints

The repo includes known-good results for each stage:

| Command | Gives you |
|---|---|
| `uv run workshop checkpoint 02-dashboard-built` | The finished dashboard |
| `uv run workshop checkpoint 02b-dashboard-extended` | The dashboard with a new colour scheme, an animation and a map |
| `uv run workshop checkpoint 03-agent-built` | The finished travel agent (and dashboard) |
| `uv run workshop checkpoint 03b-agent-extended` | The travel agent with alternate flights and moving the meeting, plus evals for both |

Their source is in `checkpoints/`, so you can read exactly what the factory produced.

## Learn more about Mantle

The full Mantle docs are in `templates/mantle_agent/.rasa/docs/mantle/` once `setup.sh` has run. Start
with `llms.txt`, which is an index. The foreman in `foreman/` is a small, complete example: one skill,
three MCP tools, and evaluation scenarios in `foreman/eval/`.
