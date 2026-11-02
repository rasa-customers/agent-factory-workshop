## What the factory always includes

The travel agent in Breakout 2 drives this dashboard, so these parts are fixed whatever the brief says.

It has four panels:

1. **Flight**: flight number and airline, status (e.g. "Delayed"), how many minutes late, the gate (and
   the gate it changed from, if it changed), terminal, and the estimated arrival time.
2. **Weather when you land**: temperature, conditions, and anything that matters for getting around
   (rain, wind).
3. **Your meeting**: title, start time, and address.
4. **Will you make it?**: a clear yes / tight / no verdict, the minutes of slack (or how late you'd be),
   and a one-line reason.

Before any data arrives, each panel shows a calm empty state (for example "Waiting for flight details…").

The dashboard updates live while someone talks to an assistant, so panels must change the moment new
data arrives, without reloading. The server is already written; it holds the state and streams changes:

- `GET api/state` returns `{"flight": {...}|null, "weather": {...}|null, "meeting": {...}|null, "verdict": {...}|null}`
- `EventSource("api/events")` sends a `state` event whose data is that same JSON whenever anything changes.

Each panel's data is a JSON object whose keys aren't fixed in advance: show the fields you recognise
(like `gate`, `previous_gate`, `delay_minutes`, `estimated_arrival`, `temperature_c`, `condition`,
`start`, `address`, `status`, `slack_minutes`, `reason`) nicely. The verdict always arrives as
`{"status": "yes"|"tight"|"no", "slack_minutes": <number, negative if late>, "reason": "..."}`, so the big
yes / tight / no comes from `status`. Show any other fields as simple
label/value rows so nothing is ever hidden. Show ISO times as the clock time written in them, which is local time where it happens:
`2026-11-03T13:15:00-05:00` shows as 1:15 PM for every viewer, whatever their own time zone.

Panels grow to fit their content (never clip or cut text off) and the page scrolls if it has to.
A small "Clear" button in a corner empties every panel back to its waiting state (`POST ./api/reset`).
