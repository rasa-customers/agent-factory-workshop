# Agent Factory Workshop

Tell an agent what you want to build. It builds it, checks it, fixes it, and hands you a link — then you
use the same factory to build **another agent**.

Built with [Rasa Mantle](https://rasa.com) (the conversational agent you talk to, and the agent it
builds) and the [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/) (the factory's
builder and checker).

**→ Start here: [the guide](guide/README.md)**

## The idea

> A software factory turns a description into working, checked software without a person in the loop
> between the request and the result. "Dark" means the lights can be off: nobody watches the line. The
> human writes what they want and judges what comes out. The factory needs four things to earn that: a
> clear spec, a builder, an independent check, and a way to feed failures back to the builder.
>
> And an agent is just software — so the same factory can build agents.

## What's in here

| Folder | What it is |
|---|---|
| `foreman/` | The Mantle agent you talk to. Its tools are the factory's. |
| `factory/` | The factory: builder and checker agents (OpenAI Agents SDK), the build loop, a live activity page. |
| `prompts/` | The two specs used in the workshop: a flight dashboard, and a travel agent. |
| `templates/` | What each build starts from. |
| `travel_mcp/` | The tools the travel agent uses: flight, weather (live, Open-Meteo), meeting, travel time, dashboard. |
| `checkpoints/` | Known-good results, if you want to skip ahead. |
| `guide/` | Step-by-step instructions, for the room or on your own. |
| `infra/` | How the workshop itself ran: sign-up portal, LLM key proxy, cloud machines. You don't need it. |

## Quick start

```bash
./setup.sh --llm-key sk-... --license <rasa-license>
uv run workshop up
```

Then open the foreman link it prints and paste in `prompts/01-dashboard.md`. Details are in the
[guide](guide/01-get-set-up.md).
