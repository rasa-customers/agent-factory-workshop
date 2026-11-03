# 1. Get set up

## In the room: the portal

> **Only for the live session on November 3, 2026.** The portal, the workshop keys and the cloud machines
> are shut down afterwards. On your own? Follow [Run it yourself](../README.md#run-it-yourself) in the
> README instead (your own OpenAI key, a free Rasa license, then "On your laptop" below).

Go to **https://portal.factory-workshop.playground-cse.rasa-dev.io** and enter your email (and the event code
`darkfactory` if it asks; the QR code on the first slide fills it in for you). You get:

1. **An LLM key** — capped for the workshop and switched off afterwards.
2. **A Rasa developer license** — request one at
   <https://rasa.com/rasa-pro-developer-edition-license-key-request> (it arrives by email in a minute or
   two) and paste it into the portal. No license yet? Carry on and add it later.
3. **A choice:** run it on your laptop, or in the cloud.

Not in the room? Skip the portal: get a license from the link above, use your own OpenAI key, and follow
"On your laptop".

## In the cloud (iPad, Windows, any browser)

Choose **In the cloud**. Your machine starts in 2–3 minutes and everything is already running. When it's
ready the portal shows:

- **Talk to the foreman →** — this is where you'll work. Go straight to [Breakout 1](02-breakout-1-dashboard.md).
- **Open the code editor** — the repo, a terminal, and the logs, in your browser (the password is on the portal).

If the portal says all machines are taken, pair with a neighbour — or tell a Rasa person and we'll add more.

## On your laptop

Needs **macOS, Linux, or Windows with WSL**, and **Python 3.11–3.13**. You should be comfortable in a
terminal; we won't cover Python basics.

In the room, choose **On my laptop** and paste the one-liner the portal shows you (it includes the
workshop proxy's `--base-url`). On your own, use your OpenAI key; the base URL defaults to OpenAI:

```bash
git clone https://github.com/rasa-customers/agent-factory-workshop.git && cd agent-factory-workshop \
  && ./setup.sh --llm-key <your OpenAI key> --license <your Rasa license>
```

`setup.sh` installs [uv](https://docs.astral.sh/uv/) (and Python 3.12 if you need it), the Python
packages, a headless Chromium for the checker, and the Mantle docs. It writes your keys to `.env` and
finishes by running `workshop doctor`.

Then start everything:

```bash
uv run workshop up
```

When it's ready you'll see:

```
│  Talk to the foreman:   http://localhost:5005/webhooks/inspector/inspect.html?...
│  Dashboard:             http://localhost:8600/
│  Build activity:        the foreman gives you a link when a build starts
```

| What | Where | What it is |
|---|---|---|
| Foreman | `localhost:5005` (the Inspector) | The Mantle agent you talk to. It runs the factory for you. |
| Factory | `localhost:8800` | Builds and checks things. Each build gets a live activity page. |
| Dashboard | `localhost:8600` | Starts as a placeholder; the factory replaces it in Breakout 1. |
| Travel agent | `localhost:5006` | Appears once the factory builds it in Breakout 2. |
| Travel tools | `localhost:8700` | The flight, weather, meeting and dashboard tools (an MCP server). |

Open the foreman link. You're ready for [Breakout 1](02-breakout-1-dashboard.md).

## Troubleshooting

| You see | Do this |
|---|---|
| `requires Python >=3.11` or `uv` can't find Python | Run `uv python install 3.12` and run `./setup.sh` again. |
| `setup.sh` fails on Windows | Run it inside WSL (`wsl --install`, then open an Ubuntu terminal), not PowerShell. |
| `doctor`: `RASA_LICENSE is missing` | Add `RASA_LICENSE=...` to `.env`, or re-run `./setup.sh --license <license>`. |
| `doctor`: base URL must end in `/v1` | Fix `OPENAI_BASE_URL` in `.env`. |
| A build stops with "out of budget" (or a 429) | Your workshop key hit its cap — ask a Rasa person to top it up. |
| "The LLM service is busy" | Rate limited: wait a minute and start the build again. |
| Anything else | Look in `workspace/logs/` — one log per service. |
