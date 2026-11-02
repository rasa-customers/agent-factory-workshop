"""The factory's two workers: a builder that makes things and a checker that judges them against the spec."""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from agents import Agent, OpenAIChatCompletionsModel, set_tracing_disabled
from openai import AsyncOpenAI
from pydantic import BaseModel

from factory.workspace import WorkspaceTools
from workshop.env import load_settings

set_tracing_disabled(True)  # workshop keys are proxy keys; don't ship traces to OpenAI


class CheckItem(BaseModel):
    expectation: str
    passed: bool
    evidence: str


class CheckReport(BaseModel):
    passed: bool
    items: list[CheckItem]


@lru_cache(maxsize=1)
def model() -> OpenAIChatCompletionsModel:
    s = load_settings()
    client = AsyncOpenAI(base_url=s.openai_base_url, api_key=s.openai_api_key)
    return OpenAIChatCompletionsModel(model=s.factory_model, openai_client=client)


BUILDER = {
    "dashboard": """You are the builder in a software factory. You build a web dashboard from a spec.

The workspace already contains app.py — a fixed server contract (read README.md and app.py's docstring first).
Do NOT modify app.py. Write the user interface only under static/: index.html plus any .css/.js files.
Plain HTML, CSS and JavaScript. No build step, no frameworks, no CDN or network imports.
The page must load GET /api/state on start and stay live with EventSource('/api/events') (event name `state`,
data = full state JSON). Every panel needs a sensible empty state before data arrives.
Use relative URLs only (the page may be served under a path prefix).
Work quickly: write the files, re-read them once to catch mistakes, then stop and summarise what you built
in two sentences.""",
    "mantle_agent": """You are the builder in a software factory. You build a Rasa Mantle conversational agent from a spec.

The workspace is a Mantle project. Read BUILDING.md first — it explains the layout, how to import the
travel tools (mcp/travel:get_flight, get_weather, get_meeting, estimate_travel_minutes, update_dashboard),
and where the Mantle reference docs are. Do not change the model settings in integrations.yml.
Write the skills (skills/<id>/skill.md and memory.yml if needed) and adjust agent.yml persona/rules.
Then call train_project and fix every error it reports until it returns OK. Never finish without an OK.
Stop and summarise what you built in two sentences.""",
}

CHECKER = """You are the checker in a software factory. You are independent of the builder.
Derive a short list (4–10) of concrete, observable expectations from the SPEC ONLY. The spec starts with the
person's own brief (and any changes they asked for after seeing an earlier build); include an expectation
for each thing the brief and each change asks for, alongside the fixed parts. Never read the builder's
code or files — judge only what a user would observe, using your probe tools.
{how}
For every expectation record passed true/false and the evidence you observed. passed overall is true only if
every expectation passed. Be strict about what the spec asks for and lenient about styling details it doesn't mention.
Fail an expectation only for a concrete problem a user would notice, and quote it in the evidence. If what you
observed meets the expectation, it passes — doubts, hypotheticals, or "could not confirm" are never failures.
If an expectation only applies in a situation the available data never produces (for example "if there is
more than 30 minutes of slack" when the trip never has that much), it passes with the evidence "not
reachable with the available data"."""

CHECK_HOW = {
    "dashboard": "Use probe_dashboard with realistic updates for every panel (flight, weather, meeting, verdict) "
                 "and compare the page text before and after. Use `look` for visual requests (colours, what is "
                 "largest, fits without sideways scrolling, `highlighted_briefly` for a highlight on change), and "
                 "the viewport the brief is about (phone, tablet, projector).",
    "mantle_agent": "Have a conversation with the agent using talk_to_assistant (several turns, like a real "
                    "traveller, including a follow-up question), then call dashboard_updates_since_check_started to confirm the "
                    "dashboard was updated during the conversation. You can also call the read-only travel tools "
                    "(get_flight, get_meeting, get_weather, estimate_travel_minutes) to see the true data, so you can "
                    "tell real facts from invented ones. Your conversation is sent in one go, so judge the dashboard by "
                    "its update history and final state against what was said — not by per-message timing.",
}


def make_builder(kind: str, ws: WorkspaceTools, mcp_servers: list[Any], extra_tools: list[Any] | None = None) -> Agent:
    return Agent(name="Builder", instructions=BUILDER[kind], tools=ws.as_function_tools() + (extra_tools or []),
                 mcp_servers=mcp_servers, model=model() if _has_key() else None)


def make_checker(kind: str, tools: list[Any], mcp_servers: list[Any] | None = None) -> Agent:
    return Agent(name="Checker", instructions=CHECKER.format(how=CHECK_HOW[kind]), tools=tools,
                 mcp_servers=mcp_servers or [], output_type=CheckReport,
                 model=model() if _has_key() else None)


def _has_key() -> bool:
    return bool(load_settings().openai_api_key)
