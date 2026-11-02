# Build an agent that builds agents — the guide

You describe what you want. A **factory** builds it, checks it, fixes it, and hands you a link.
You'll use it twice: first to build a live flight dashboard, then to build a conversational travel agent
that drives that dashboard. Agents building agents.

This guide works in the room and on your own afterwards.

| Step | What you do | Time |
|---|---|---|
| [1. Get set up](01-get-set-up.md) | Get a key, run the factory on your laptop or in the cloud | 10–20 min |
| [2. Breakout 1 — the dashboard](02-breakout-1-dashboard.md) | Ask the factory for a dashboard and watch it build | ~5 min of building |
| [3. Breakout 2 — the travel agent](03-breakout-2-agent.md) | Ask the factory for an agent that uses the dashboard | ~5 min of building |
| [4. Voice (optional)](04-voice-optional.md) | Talk to your agents instead of typing | 5 min |
| [5. After the workshop](05-after-the-workshop.md) | Use your own key, build something else | — |

## The idea in 60 seconds

A **software factory** turns a description into working, checked software without a person in the loop
between the request and the result. **"Dark"** means the lights can be off: nobody watches the line. You
write what you want and judge what comes out.

It needs four things to earn that:

1. **A spec** — a clear description of what "done" looks like: the brief you agree with the foreman, plus a fixed contract (`factory/contracts/`).
2. **A builder** — an agent that writes the thing (OpenAI Agents SDK, `factory/agents.py`).
3. **An independent check** — a second agent that never reads the code, only uses the result the way
   you would, and says pass or fail with evidence.
4. **A feedback loop** — failures go back to the builder until the check passes (up to 3 rounds).

Around that loop sits a second, slower one, and it's yours: you look at what came back and tell the
foreman what to change. The factory builds on what it made, and the checker holds it to every change
from then on.

And an agent is just software — so the same factory can build agents.

```
 you ──▶ Foreman (Rasa Mantle agent) ──▶ Factory (OpenAI Agents SDK)
                                            │  builder ─▶ build ─▶ checker
                                            │     ▲                   │
                                            │     └──── failures ─────┘
                                            ▼
                                   dashboard / travel agent ──▶ a link for you
```

The **foreman** is the agent you talk to. It's a Rasa Mantle agent whose only tools are the factory's:
`start_build`, `build_status`, `build_result`.
