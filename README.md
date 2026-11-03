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
| `prompts/` | Opening lines for the two builds, if you're not sure what to say to the foreman. |
| `factory/contracts/` | The fixed part of every spec the factory adds to your brief. |
| `templates/` | What each build starts from. |
| `travel_mcp/` | The tools the travel agent uses: flight, weather (live, Open-Meteo), meeting, travel time, dashboard. |
| `checkpoints/` | Known-good results, if you want to skip ahead. |
| `foreman/eval/`, `templates/mantle_agent/eval/` | Mantle evals (simulated conversations) for the foreman and for every built agent: `uv run workshop eval foreman` or `agent`. |
| `guide/` | Step-by-step instructions, for the room or on your own. |
| `infra/` | How the workshop itself ran: sign-up portal, LLM key proxy, cloud machines. You don't need it. |

## Run it yourself

You need **macOS, Linux, or Windows with WSL**, plus `git`. `setup.sh` installs everything else
([uv](https://docs.astral.sh/uv/), Python 3.12 if you don't have 3.11–3.13, the Python packages, and a
headless Chromium the checker uses).

**1. Get an OpenAI API key.** Create one at <https://platform.openai.com/api-keys>. The factory, the
foreman and the agents it builds all use `gpt-5.2` by default (`FACTORY_MODEL` in `.env`), so the key
needs access to that model. A dashboard build costs cents; a travel-agent build somewhat more.

**2. Get a free Rasa Developer Edition license.** Request one at
<https://rasa.com/rasa-pro-developer-edition-license-key-request>. It arrives by email in a minute or two.

**3. Clone the repo and run the setup script** with both keys:

```bash
git clone https://github.com/rasa-customers/agent-factory-workshop.git
cd agent-factory-workshop
./setup.sh --llm-key sk-... --license <your-rasa-license>
```

It writes your keys to `.env` (only readable by you), downloads the Mantle docs the factory reads while
building agents, and finishes with `workshop doctor`, which tells you if anything is missing.

**4. Start everything:**

```bash
uv run workshop up
```

It prints a link to the **foreman**, the agent you talk to. Open it.

**5. Build the dashboard.** Tell the foreman what you want, or paste the opening line from
`prompts/01-dashboard.md`. Answer its questions, read the brief, say yes, and follow the link to watch
the build. Steps: [guide/02-breakout-1-dashboard.md](guide/02-breakout-1-dashboard.md).

**6. Build the travel agent** that drives the dashboard, starting from `prompts/02-travel-agent.md`.
Steps: [guide/03-breakout-2-agent.md](guide/03-breakout-2-agent.md).

Stuck at any point? `uv run workshop checkpoint` jumps to a known-good dashboard or agent. Optional: add a
`DEEPGRAM_API_KEY` to `.env` to talk to your agents out loud ([guide/04-voice-optional.md](guide/04-voice-optional.md)).
