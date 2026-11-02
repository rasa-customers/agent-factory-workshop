# 2. Breakout 1 — build the dashboard

You'll ask the factory for a live flight dashboard, watch it build and check its own work, then play with
the result.

## Start the build

1. Open [`prompts/01-dashboard.md`](../prompts/01-dashboard.md) (in the cloud, open it in the code editor)
   and copy all of it.
2. Paste it into the foreman and send it.

The foreman starts the build straight away and replies with a link to the build's **activity page** — click
the link button under its message.

> **Why it works — the spec.** The prompt is a spec: what's on each panel, what "empty" looks like, how
> data arrives, what it should look like on a projector. The clearer the spec, the less the factory has
> to guess, and the more the checker can actually check.

## Watch it work

Open the activity page. It updates live, in three columns:

- **Builder** — an OpenAI Agents SDK agent reading the template, writing `static/index.html`, and
  sanity-checking its own files.
- **Checker** — a *different* agent. It never sees the code. It opens the dashboard in a headless
  browser, sends it realistic updates for every panel, and reports pass or fail per expectation, with
  what it actually saw.
- **Factory** — the line itself: rounds, starting the build, the final verdict.

> **Why it works — the builder.** The builder works in a small, pre-shaped workspace
> (`templates/dashboard/`): the server and its data contract already exist, and the README there tells it
> the rules. A narrow job is a fast, reliable job.

> **Why it works — an independent check.** The checker judges from the spec alone, the way a user would.
> It can't be talked into passing code it never read.

If the checker fails something, you'll see a ✗ with the evidence, then **Round 2** — the builder gets
exactly those failures and fixes them.

> **Why it works — the feedback loop.** Failures go back to the builder as concrete, observed problems
> ("the weather panel cut off the wind value"), not "try again". Most builds pass in one or two rounds.

It usually takes 1–3 minutes. You can also ask the foreman "how's it going?".

## Use it

When it passes, the activity page and the foreman give you the dashboard link (`localhost:8600` on a
laptop). The factory fills it with the workshop's example trip (the flight, live New York weather when
you land, the meeting, and a verdict), so it's alive straight away. Press **Clear** to empty it, then send
it data yourself from a terminal:

```bash
curl -s localhost:8600/api/state -H 'content-type: application/json' \
  -d '{"panel":"flight","data":{"flight_number":"RA 2026","status":"Delayed","delay_minutes":40,"gate":"B22","previous_gate":"B14"}}'
```

Things to try:

- Send the `weather`, `meeting` and `verdict` panels too (`{"status":"tight","slack_minutes":5,"reason":"..."}`).
- Add a field nobody asked for — it should still show up.
- Open the dashboard on your phone or a second window; both update live.
- `curl -s -X POST localhost:8600/api/reset` to clear it.

In Breakout 2, an agent sends these updates for you.

## If it doesn't pass

After three rounds the factory stops and tells you why. Load the known-good dashboard and carry on:

```bash
uv run workshop checkpoint 02-dashboard-built
```

Then [Breakout 2](03-breakout-2-agent.md).
