---
name: Alternate flights (tool-backed options)
description: |
  Use when the traveller is predicted to be tight or late (slack under 15 minutes) and they accept an offer
  to look for alternate flights, or they explicitly ask for alternate/earlier flights. Use tool-backed flight
  options only (find_alternate_flights) and never invent flight numbers/times. Propose a few alternates and,
  if the traveller selects one, update the dashboard plan (flight/weather/route/verdict) accordingly.
import_tools:
  - mcp/travel:get_flight
  - mcp/travel:get_meeting
  - mcp/travel:estimate_travel_minutes
  - mcp/travel:find_alternate_flights
  - mcp/travel:get_weather
  - mcp/travel:update_dashboard
---

# Goal
When the plan is **tight** (<15 min slack) or **no** (late), offer and (when accepted) find alternate flights that get the traveller to the destination with **time to spare** (>=15 minutes slack to the meeting after deplaning + ground travel).

# Non-negotiables (checker-critical)
- **Every alternate flight you mention in chat must come from `find_alternate_flights`.**
- **Every buffer/slack claim for an alternate must be backed by your own `estimate_travel_minutes` call using that alternate’s `arrival_airport` and `estimated_arrival`.**
- Do not guess gates, delays, seat counts, departs/arrivals, or ETAs.
- There is no booking tool: never claim you rebooked; you can only update the **plan/dashboard**.

# Procedure

## 1) Fetch current facts and confirm we are actually tight/late
Call:
- `get_flight`
- `get_meeting`

Compute the current verdict (same method as Trip monitor):
- Decide `mode`: default `car`, use `subway` only if the traveller asked for it.
- `depart_at` = current flight `estimated_arrival` + 15 minutes.
- Call `estimate_travel_minutes` with `origin` = the current flight arrival airport, `destination_address` = meeting `address`.
- Compute `slack_minutes` vs meeting `start`; status is yes/tight/no.

If status is `yes` with slack_minutes >= 15, do **not** search; tell them they already have >=15 minutes of buffer.

## 2) Find alternates (tool-backed)
Call `find_alternate_flights`.

For each returned candidate flight, compute its meeting buffer:
- `depart_at` = candidate `estimated_arrival` + 15 minutes.
- Call `estimate_travel_minutes` with:
  - `origin` = candidate `arrival_airport`
  - `destination_address` = meeting `address`
  - `depart_at` as above
  - `mode` = chosen mode
- Compute candidate `slack_minutes` vs meeting start.

Rank candidates by:
1) status (prefer `yes`),
2) highest slack_minutes,
3) earliest `estimated_arrival`.

Select up to 3 to present.

## 3) Present options without inventing details
In chat:
- 1 short sentence: you found alternates.
- Bullets (2–3): each bullet includes **only fields returned by tools**:
  - `{airline} {flight_number}`
  - `departs` and `estimated_arrival`
  - `arrival_airport`
  - your computed buffer: “~X min buffer” (or “still tight/late by ~Y min”)
  - optionally include `seats_left` only if returned.
- Ask them to pick one by letter/flight number.

If none achieve >=15 minutes buffer:
- Say none restore a full 15-minute buffer.
- Still list the best 2–3 options with their computed slack/late so they can choose.

## 4) When the traveller chooses an option, update the plan/dashboard
After the user picks a specific alternate flight (must clearly match one you listed from the tool):

1) Update `flight` panel to reflect the planned flight = chosen alternate.
   - Include: `flight_number`, `airline`, `departs`, `estimated_arrival`, `arrival_airport`.
   - Optionally include `original_flight` from `get_flight` as extra keys (but don’t clutter chat).

2) Weather: call `get_weather` with:
   - `location` = the *destination city/airport from tools* (use the current flight tool’s `destination` or the chosen flight’s location as returned; do not guess a city name)
   - `at` = chosen `estimated_arrival`
   Then update the `weather` panel.

3) Route + verdict: call `estimate_travel_minutes` for the chosen alternate (same as above) and update:
- `route` panel with `{from, to, mode, minutes}` from the route tool.
- `verdict` panel with exactly `{status, slack_minutes, reason}` where `reason` mentions the ground travel minutes.

In chat, confirm the plan is updated and restate the new verdict briefly.
