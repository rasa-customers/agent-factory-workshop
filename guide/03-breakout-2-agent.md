# 3. Breakout 2 — build the travel agent

Same factory, different product: this time it builds a **Rasa Mantle conversational agent** — the kind
of agent the foreman itself is. It answers *"I'm flying to New York. Check my flight, show me the weather
when I land, and help me work out whether I'll make my meeting."* and keeps your dashboard in sync while
it talks.

## Agree the brief

Tell the foreman you want a travel agent that drives your dashboard, and what it should be like. For
example:

> Now I want a travel agent for my trip. Friendly but very short, like a good assistant texting me, and
> it should warn me about anything that could make me late.

It asks about tone, how much the agent says, and what it should point out without being asked, then
shows the brief. Change it until it's right and say **yes**. Not sure where to start? Paste
the opening line in [`prompts/02-travel-agent.md`](../prompts/02-travel-agent.md) and answer the foreman's questions.

> **Why it works — the fixed parts.** Your brief is about personality and behaviour. The factory adds the
> agent contract ([`factory/contracts/mantle_agent.md`](../factory/contracts/mantle_agent.md)): which
> tools it uses, that every fact comes from a tool, how the verdict is worked out, and that the dashboard
> stays in sync. That's the part that makes it trustworthy, so it isn't up for negotiation.

## What's different this time

- **The builder writes a Mantle project**, not a web page: skills in `skills/<id>/skill.md` that import
  the travel tools (`mcp/travel:get_flight`, `get_weather`, `get_meeting`, `estimate_travel_minutes`,
  `update_dashboard`). Its cheat sheet is `templates/mantle_agent/BUILDING.md`, and the full Mantle docs
  are in the workspace for it to search.
- **It trains what it builds** with `train_project`, and fixes whatever `rasa train` rejects before it
  says it's done.
- **The checker has a conversation.** It talks to the running agent over several turns (including
  follow-ups), reads the dashboard's update history, and looks up the real flight, weather and meeting
  data so it can tell real facts from invented ones. It also checks what your brief asked for (tone,
  length, warnings). Something the example trip can never trigger, like "if I have an hour to spare",
  passes as "not reachable".

A build takes about 2–5 minutes.

## Use it

When it passes you get a link to your new agent in the Inspector (`localhost:5006` on a laptop). Open
the dashboard next to it (the agent also gives you a link to it in its first reply), then say:

> I'm flying to New York. Check my flight, show me the weather when I land, and help me work out whether
> I'll make my meeting.

Watch the panels fill in as it answers. Then try:

1. **"What if I take the subway instead?"** — the verdict should change, on screen and on the dashboard.
2. **"Is it going to rain when I land?"** — the weather is real (Open-Meteo, for New York at your landing
   time); the flight and meeting are a fixed example.
3. **"Has my gate changed?"**

In the Inspector you can see which skill ran, which tools it called, and what it remembered.

## Make it more useful

An agent with one skill only reports. Give it skills that *do* something, one change at a time:

> Add a skill to my agent: if I'm going to be tight or late, offer to find me an alternate flight that
> gets me there with time to spare.

> Add another skill: offer to move my meeting to a later slot so I have at least 15 minutes to spare,
> and move it if I say yes.

Each one becomes its own Mantle skill, with its own description of when it applies and its own tools
(`find_alternate_flights`, `available_meeting_times`, `reschedule_meeting`). The checker holds a fresh
conversation each time and checks the new skill against the real options, so it catches an agent that
recommends a flight that would still be late.

Then try it:

1. "I'm flying to New York… will I make my meeting?" (tight: 5 minutes)
2. "Can you find me an earlier flight?" (one lands at LaGuardia with 45 minutes to spare)
3. "Could we move my meeting instead?" and pick a time. Watch the meeting and verdict panels change.

The trip resets each time the factory checks a build, so a moved meeting doesn't stick around.

Smaller changes work too: its tone, emoji status markers, ending every reply with one suggestion.

## If it doesn't pass

```bash
uv run workshop checkpoint 03-agent-built      # the trip check
uv run workshop checkpoint 03b-agent-extended  # plus alternate flights and moving the meeting
```

This starts the known-good travel agent and prints its link.

## What just happened

You described two pieces of software in plain language and got both, built and checked, without
reading or writing code. The second one is an agent — built by an agent, which you asked through an
agent. That's the dark factory: the human writes the spec and judges the result.

Next: [voice](04-voice-optional.md), or [taking it home](05-after-the-workshop.md).
