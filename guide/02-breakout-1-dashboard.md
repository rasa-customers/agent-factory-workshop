# 2. Breakout 1 — build the dashboard

You'll tell the foreman what you want, agree a short brief with it, watch the factory build and check
it, then ask for changes until you like it.

## Agree the brief

Tell the foreman about your trip and what you want, in your own words. For example:

> I'm flying to New York for a meeting and want a dashboard I can glance at on my phone in the taxi.

It asks a couple of questions (where you'll look at it, what should stand out, the look and feel), then
shows you the brief it will send: a title and a few bullets. Change anything you like ("light theme",
"make the address huge", "drop the airline name"); it shows the new version each time. When it looks
right, say **yes**. Nothing is built until you do.

Not sure what to say? Paste the opening line in [`prompts/01-dashboard.md`](../prompts/01-dashboard.md) and answer the foreman's questions. Short on time? Add "just build it".

The foreman replies with a link to the build's **activity page**. Click the button under its message.

> **Why it works — the spec.** You only describe what's yours to decide. The factory adds a fixed
> contract to every dashboard brief ([`factory/contracts/dashboard.md`](../factory/contracts/dashboard.md)):
> the four panels and the live data feed the travel agent needs in Breakout 2. Your brief plus that
> contract is the spec, and the checker tests both. The clearer the spec, the less the factory guesses and
> the more the checker can actually check.

## Watch it work

Open the activity page. It updates live, in three columns:

- **Builder** — an OpenAI Agents SDK agent reading the template, writing `static/index.html`, and
  sanity-checking its own files.
- **Checker** — a *different* agent. It never sees the code. It turns your brief and the contract into a
  list of expectations, opens the dashboard in a headless browser (at phone, tablet or projector width),
  sends it realistic updates for every panel, and reports pass or fail per expectation, with what it
  actually saw: the text, the colours, what's biggest, whether anything highlights when it changes.
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
you land, the meeting, and a verdict), so it's alive straight away.

## Change it

Look at it the way you'd look at anything someone built for you, and tell the foreman what to change:

> Make the verdict turn red when it's tight or a no.

> The reason is repeated three times. Show it once.

> I can't read the gate from across the room. Make it twice as big.

The factory doesn't start over. The builder starts from the dashboard you're looking at and makes that
change, and the checker re-checks everything, your change included. Each change is its own build with
its own activity page, usually a minute or two. Keep going until you like it.

### Make it yours

Pick one or two, in your own words:

| Ask for | What the checker looks at |
|---|---|
| A new colour scheme ("Catppuccin Mocha", "airport departure board", "your company's colours") | The page's actual colours |
| An animation when the verdict changes | Which elements animate right after an update |
| A map of the route from the airport to the meeting | Whether a map draws, with tiles, markers and the route line |
| A countdown to the meeting, or the minutes of slack as a big number | The text on the page |
| A phone layout for the taxi | The page at phone width, with nothing spilling sideways |

The map uses data the dashboard already receives (`route`: from, to, mode, minutes); in Breakout 2 your
travel agent keeps it up to date.

### More you can ask the foreman

- **"Why did that fail?"** It reads you the checker's evidence.
- **"What have I built?"** Every version, passed or failed.
- **"Show me the brief."** Your brief plus every change since.
- **"Go back to the version before the map."** Puts an earlier version back live; further changes build on it.

> **Why it works — the human's job.** In a dark factory nobody watches the line. Your work moves to the
> two ends: saying what you want, and judging what you got. Every change you ask for is one more line in
> the spec, so the checker holds the factory to it from then on.

### Send it data yourself

Press **Clear** to empty it, then send it data from a terminal:

```bash
curl -s localhost:8600/api/state -H 'content-type: application/json' \
  -d '{"panel":"flight","data":{"flight_number":"RA 2026","status":"Delayed","delay_minutes":40,"gate":"B22","previous_gate":"B14"}}'
```

- Send the `weather`, `meeting` and `verdict` panels too (`{"status":"tight","slack_minutes":5,"reason":"..."}`).
- Add a field nobody asked for — it should still show up.
- Open the dashboard on your phone or a second window; both update live.
- `curl -s -X POST localhost:8600/api/reset` to clear it.

In Breakout 2, an agent sends these updates for you.

## If it doesn't pass

After three rounds the factory stops and tells you why. Load the known-good dashboard and carry on:

```bash
uv run workshop checkpoint 02-dashboard-built      # the plain dashboard
uv run workshop checkpoint 02b-dashboard-extended  # with a colour scheme, an animation and a map
```

Then [Breakout 2](03-breakout-2-agent.md).
