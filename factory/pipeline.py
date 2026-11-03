"""The factory line: build → check → feed failures back → build again, until the checker passes."""
from __future__ import annotations

import json

import time
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any, AsyncIterator

import openai
from agents import RunContextWrapper, RunHooks, Runner

from factory.agents import CheckReport, make_builder, make_checker
from factory.checks.dashboard import probe_dashboard_tool
from factory.example_data import seed_dashboard
from factory.checks.mantle import (dashboard_history_tool, rasa_tools_server, reset_trip, train_project_tool,
                                   travel_truth_server)
from factory.hosting import ArtifactHost, StartFailed
from factory.jobs import Job, JobStore
from factory.workspace import WORKSPACE, WorkspaceTools, prepare_workspace

CHECKPOINT = {"dashboard": "02-dashboard-built", "mantle_agent": "03-agent-built"}
MAX_TURNS = 40


DETAIL_LIMIT = 4000


def clip(text: str, limit: int = DETAIL_LIMIT) -> str:
    return text if len(text) <= limit else f"{text[:limit]}\n… ({len(text) - limit:,} more characters)"


def pretty_args(raw: str) -> str:
    try:
        return json.dumps(json.loads(raw), indent=1, ensure_ascii=False)
    except (TypeError, ValueError):
        return raw or ""


class ActivityHooks(RunHooks):
    """Turns every tool call into a line on the activity page; the line expands to its arguments, then its result."""

    def __init__(self, store: JobStore, job_id: str, actor: str) -> None:
        self.store, self.job_id, self.actor = store, job_id, actor
        self.lines: dict[str, int] = {}

    def _key(self, context: Any, tool: Any) -> str:
        return getattr(context, "tool_call_id", None) or tool.name

    async def on_tool_start(self, context: RunContextWrapper, agent: Any, tool: Any) -> None:
        args = pretty_args(getattr(context, "tool_arguments", "") or "")
        self.lines[self._key(context, tool)] = self.store.add_event(
            self.job_id, self.actor, f"→ {tool.name}", detail=clip(f"Asked:\n{args}") if args else "")

    async def on_tool_end(self, context: RunContextWrapper, agent: Any, tool: Any, result: object) -> None:
        seq = self.lines.pop(self._key(context, tool), None)
        if seq is not None:
            self.store.add_detail(self.job_id, seq, clip(f"Got back:\n{result}"))


class RealWorkers:
    @asynccontextmanager
    async def session(self, job: Job, root: Path) -> AsyncIterator[SimpleNamespace]:
        ws = WorkspaceTools(root)
        async with AsyncExitStack() as stack:
            if job.kind == "dashboard":
                builder = make_builder("dashboard", ws, mcp_servers=[])

                def checker_for(url: str):
                    return make_checker("dashboard", tools=[probe_dashboard_tool(url, root)])
            else:
                check_tools = rasa_tools_server(root, "http://localhost:5006", ["talk_to_assistant"])
                truth = travel_truth_server()
                await stack.enter_async_context(check_tools)
                await stack.enter_async_context(truth)
                builder = make_builder("mantle_agent", ws, mcp_servers=[], extra_tools=[train_project_tool(root)])

                def checker_for(url: str):
                    return make_checker("mantle_agent", tools=[dashboard_history_tool(time.time())],
                                        mcp_servers=[check_tools, truth])
            yield SimpleNamespace(builder=builder, checker_for=checker_for,
                                  before_check=reset_trip if job.kind == "mantle_agent" else None)


def explain(e: Exception) -> str:
    msg = str(e)
    if "budget" in msg.lower():
        return "The workshop LLM key has run out of budget — ask a Rasa person to top it up."
    if isinstance(e, openai.RateLimitError):
        return "The LLM service is busy right now (rate limited). Wait a minute and start the build again."
    if isinstance(e, openai.AuthenticationError):
        return "The LLM key was rejected — check OPENAI_API_KEY and OPENAI_BASE_URL in .env."
    return f"The factory hit an error: {msg[:300]}"


def builder_input(spec: str, failures: list[str], change: str | None = None) -> str:
    text = f"SPEC:\n{spec}"
    if change:
        text = (f"This workspace already holds a finished build that passed an earlier version of this spec. "
                f"The person has seen it and asked for one change:\n\n  {change}\n\n"
                f"Make that change and keep everything else working as it does now; don't start over.\n\n{text}")
    if not failures:
        return text
    bullet = "\n".join(f"- {f}" for f in failures)
    return f"{text}\n\nThe independent checker rejected your last build. Fix these and nothing else:\n{bullet}"


async def run_job(job: Job, store: JobStore, *, run_agent=Runner.run, host=None, workers=None, seed=None,
                  max_rounds: int = 3, workspace_base: Path = WORKSPACE) -> None:
    host = host or ArtifactHost()
    workers = workers or RealWorkers()
    say = lambda actor, text: store.add_event(job.id, actor, text)  # noqa: E731
    try:
        root = prepare_workspace(job, base=workspace_base)
        if job.restore:
            say("factory", f"Putting build {job.based_on} back live.")
            url = await host.start(job.kind, root)
            await host.promote(job.kind, root)
            if job.kind == "dashboard" and await (seed or seed_dashboard)("http://localhost:8600"):
                say("factory", "Filled the dashboard with the workshop's example trip.")
            store.update(job.id, state="passed", result_url=url, summary=f"Build {job.based_on} is live again.")
            say("factory", f"Done. Build {job.based_on} is live again: {url}")
            return
        if job.change:
            say("factory", f"Starting from build {job.based_on} and changing: {job.change}")
        say("factory", f"Workspace ready. Up to {max_rounds} build rounds.")
        async with workers.session(job, root) as crew:
            failures: list[str] = []
            for rnd in range(1, max_rounds + 1):
                store.update(job.id, state="building" if rnd == 1 else "fixing", round=rnd)
                told = builder_input(job.spec, failures, job.change)
                store.add_event(job.id, "builder",
                                f"Round {rnd}: building." if rnd == 1 else f"Round {rnd}: fixing {len(failures)} problem(s).",
                                detail=f"What the builder was told:\n\n{told}")
                built = await run_agent(crew.builder, told,
                                        hooks=ActivityHooks(store, job.id, "builder"), max_turns=MAX_TURNS)
                summary = str(built.final_output)
                say("builder", summary)

                store.update(job.id, state="checking")
                say("factory", "Starting what was built so it can be checked.")
                try:
                    url = await host.start(job.kind, root)
                except StartFailed as e:
                    say("factory", f"Couldn't start it — sending the errors back to the builder. {e}"[:600])
                    failures = [str(e)]
                    continue
                if getattr(crew, "before_check", None):
                    await crew.before_check()
                say("checker", "Checking the result against the spec (without looking at the code).")
                checked = await run_agent(crew.checker_for(url), f"SPEC:\n{job.spec}",
                                          hooks=ActivityHooks(store, job.id, "checker"), max_turns=MAX_TURNS)
                rep: CheckReport = checked.final_output
                for item in rep.items:
                    say("checker", f"{'✓' if item.passed else '✗'} {item.expectation} — {item.evidence}")
                store.update(job.id, check_report=[i.model_dump() for i in rep.items])
                if rep.passed:
                    await host.promote(job.kind, root)
                    if job.kind == "dashboard":
                        if await (seed or seed_dashboard)("http://localhost:8600"):
                            say("factory", "Filled the dashboard with the workshop's example trip so you can see it live.")
                    store.update(job.id, state="passed", result_url=url, summary=summary)
                    say("factory", f"Passed in round {rnd}. Open it: {url}")
                    return
                failures = [f"{i.expectation} (checker saw: {i.evidence})" for i in rep.items if not i.passed]
        missing = "; ".join(failures) or "the checker did not pass it"
        store.update(job.id, state="failed",
                     error=(f"Still failing after {max_rounds} rounds: {missing}. "
                            f'To carry on with a known-good version, run "uv run workshop checkpoint {CHECKPOINT[job.kind]}".'))
        say("factory", "Out of rounds — marked failed.")
    except Exception as e:  # noqa: BLE001 — every failure must end as a readable state for the foreman
        store.update(job.id, state="failed", error=f"{explain(e)} To carry on with a known-good version, run "
                                                   f'"uv run workshop checkpoint {CHECKPOINT[job.kind]}".')
        say("factory", f"Stopped: {explain(e)}")
