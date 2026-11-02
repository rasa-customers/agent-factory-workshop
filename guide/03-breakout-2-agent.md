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
shows the brief. Change it until it's right and say **yes**. Short on time? Paste
[`prompts/02-travel-agent.md`](../prompts/02-travel-agent.md) and say yes.

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

## Change it

Tell the foreman what you'd change, just as with the dashboard:

> Start every reply with a status emoji: green for yes, yellow for tight, red for no.

> It never tells me what to do. End each reply with one suggestion.

The builder edits the agent it already made, trains it again, and the checker holds a fresh
conversation to check the change and everything else.

## If it doesn't pass

```bash
uv run workshop checkpoint 03-agent-built
```

This starts the known-good travel agent and prints its link.

## What just happened

You described two pieces of software in plain language and got both, built and checked, without
reading or writing code. The second one is an agent — built by an agent, which you asked through an
agent. That's the dark factory: the human writes the spec and judges the result.

Next: [voice](04-voice-optional.md), or [taking it home](05-after-the-workshop.md).
