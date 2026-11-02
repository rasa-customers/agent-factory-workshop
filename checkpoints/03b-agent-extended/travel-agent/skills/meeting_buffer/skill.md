---
name: Restore meeting buffer (reschedule if tight)
description: |
  Use when the computed arrival-to-meeting slack is under 15 minutes and the traveller wants more buffer.
  Offer later meeting times that restore at least 15 minutes of slack using tool-backed availability; only
  reschedule after an explicit yes to a specific proposed time. After rescheduling, recompute the route/verdict
  and update the dashboard.
import_tools:
  - mcp/travel:get_flight
  - mcp/travel:get_meeting
  - mcp/travel:estimate_travel_minutes
  - mcp/travel:available_meeting_times
  - mcp/travel:reschedule_meeting
  - mcp/travel:update_dashboard
---

# Goal
When the traveller’s expected arrival at the meeting leaves **under 15 minutes** of buffer (or they’re late), proactively offer to move the meeting later to restore **at least 15 minutes** of slack.

# Steps

## 1) Fetch current facts
Call:
- `get_flight`
- `get_meeting`

## 2) Compute current slack (same rules as the trip monitor)
- Default ground travel mode is `car` unless the traveller asked about subway.
- Set `depart_at` = flight `estimated_arrival` + 15 minutes.
- Call `estimate_travel_minutes` with `origin` = flight arrival airport, `destination_address` = meeting address, `depart_at`, and chosen `mode`.
- Compute `slack_minutes` as minutes between meeting start and route `arrives_at` (negative if late).

If `slack_minutes` >= 15, **do not** offer rescheduling.

## 3) If slack is under 15, get tool-backed later slots
Call `available_meeting_times` to get `{current_start, slots}`.

For each candidate slot, compute whether it restores at least 15 minutes slack:
- Use the same route estimate result (same `arrives_at`).
- `new_slack_minutes` = minutes between candidate slot time and `arrives_at`.
- Keep only slots where `new_slack_minutes >= 15`.

If none qualify, say so briefly and offer other options (e.g., leave ASAP; if traveller asks, try subway), but **do not invent times**.

## 4) Present options (tool-backed) and ask for a specific confirmation
In chat:
- Explain you’re tight/late and you can move the meeting later to restore buffer.
- Present up to **3 options**, and every option MUST be one of the returned `slots`.
- Ask the traveller to choose one of those options (or say no).

Important:
- Do not propose generic times like “2:45/3:00/3:30” unless they appear in `slots`.
- If the traveller says “yes/do it” without selecting a time, ask: “Which time should I move it to: A, B, or C?” and wait.

## 5) Reschedule only after explicit confirmation of a specific slot
When the traveller confirms one specific proposed time:
1) Call `reschedule_meeting` with `start` = that exact slot.
2) If `{ok: true}`:
   - Update `meeting` panel with the returned `meeting`.
   - Recompute `slack_minutes` vs the new meeting start (route is unchanged unless mode changes).
   - Update `route` panel with `{from, to, mode, minutes}` from `estimate_travel_minutes`.
   - Update `verdict` panel with `{status: yes|tight|no, slack_minutes, reason}` where `reason` is one plain sentence that mentions the ground travel minutes.
3) If `{ok: false}`:
   - Tell the traveller you couldn’t move it; do not claim it changed; do not update the meeting panel.

# Guardrails
- Never reschedule without explicit traveller confirmation of a specific time.
- Never ask the traveller for flight/meeting details; always use tools.
- Keep chat concise; use bullets for options and next steps.
