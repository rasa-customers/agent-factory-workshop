"""`workshop eval`: Mantle's simulated-conversation evals, against the foreman or the latest built agent.

An LLM plays the user from each scenario in eval/scenarios/, a second LLM judges the conversation, and the
assertions check what the agent actually did (skills, memory, tool calls). Runs through the same Rasa MCP
tools a coding agent would use (`validate_scenario`, `evaluate_agent`). The agent must be running.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
from datetime import timedelta
from pathlib import Path

from workshop.procs import REPO, WORKSPACE

TARGETS = {
    "foreman": (REPO / "foreman", "http://localhost:5005"),
    "agent": (WORKSPACE / "latest-agent", "http://localhost:5006"),
}
AGENT_TEMPLATE = REPO / "templates" / "mantle_agent"


def scenario_paths(project: Path, names: list[str]) -> list[str]:
    """Scenario files relative to the project: every eval/scenarios/*.yml, or the ones named (with or without folder and .yml)."""
    folder = Path(project) / "eval" / "scenarios"
    found = sorted(p.name for p in folder.glob("*.yml"))
    if not names:
        return [f"eval/scenarios/{n}" for n in found]
    picked = []
    for name in names:
        file = Path(name).name if name.endswith(".yml") else f"{Path(name).name}.yml"
        if file not in found:
            raise SystemExit(f"No scenario {name!r}. Scenarios: {', '.join(n[:-4] for n in found) or 'none'}")
        picked.append(f"eval/scenarios/{file}")
    return picked


def seed_eval(project: Path, template: Path = AGENT_TEMPLATE) -> None:
    """Copy the template's eval files into a build that lacks them; never overwrite what is already there."""
    for src in (Path(template) / "eval").rglob("*.yml"):
        dest = Path(project) / src.relative_to(template)
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)


def summarize(result: dict) -> tuple[str, int]:
    if result.get("success") is False or result.get("error"):
        return f"✗ The evaluation didn't run: {result.get('error') or result.get('message')}", 1
    lines, failed = [], False
    for s in result.get("scenario_results", []):
        ok = s["runs_total"] > 0 and s["runs_passed"] == s["runs_total"]
        failed |= not ok
        lines.append(f"  {'✓' if ok else '✗'} {s['scenario_name']}  {s['runs_passed']}/{s['runs_total']}"
                     + (f"  ({s['runs_errored']} errored)" if s.get("runs_errored") else ""))
    folder = str(Path(result.get("summary_path", "")).parent)
    lines.append(f"\nReports (one per run, with the transcript and the judge's reasons): {folder}")
    return "\n".join(lines), int(failed)


async def _evaluate(project: Path, url: str, batches: list[list[str]], runs: int, before_each=None) -> dict:
    """Run each batch of scenarios in turn (scenarios in one batch run at the same time) into one results folder."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "rasa", "tools", "run", "--mode", "stdio", "--project-path", str(project), "--rasa-server-url", url],
        env=dict(os.environ), cwd=str(project))

    async def call(session, tool: str, args: dict) -> dict:
        return json.loads((await session.call_tool(tool, args)).content[0].text)

    merged: dict = {"scenario_results": []}
    with open(os.devnull, "w") as quiet:
        async with stdio_client(params, errlog=quiet) as (read, write):
            async with ClientSession(read, write, read_timeout_seconds=timedelta(minutes=20)) as session:
                await session.initialize()
                for path in (p for batch in batches for p in batch):
                    check = await call(session, "validate_scenario", {"scenario_path": path})
                    if not check.get("success"):
                        return {"success": False, "error": f"{path} is not a valid scenario: {check.get('errors')}"}
                for batch in batches:
                    if before_each:
                        await before_each()
                    args = {"scenario_paths": batch, "run_count": runs}
                    if merged.get("experiment_timestamp"):
                        args["experiment_timestamp"] = merged["experiment_timestamp"]
                    result = await call(session, "evaluate_agent", args)
                    while result.get("status") == "running":
                        result = await call(session, "get_evaluation_status",
                                            {"experiment_timestamp": result["experiment_timestamp"]})
                    if result.get("success") is False or result.get("error"):
                        return result
                    merged["experiment_timestamp"] = result.get("experiment_timestamp")
                    merged["summary_path"] = result.get("summary_path", "")
                    merged["scenario_results"] += result.get("scenario_results", [])
    return merged


def run(target: str, names: list[str], runs: int = 1) -> int:
    from factory.hosting import wait_http
    from workshop.env import export_settings

    export_settings()
    project, url = TARGETS[target]
    if target == "agent":
        if not project.exists():
            print("No agent built yet. Build one with the foreman, or: workshop checkpoint 03-agent-built")
            return 1
        seed_eval(project)
    if not asyncio.run(wait_http(url, 5)):
        print(f"The {target} isn't running at {url}. Start it with: workshop up")
        return 1
    paths = scenario_paths(project, names)
    print(f"Running {len(paths)} scenario(s) against the {target}, {runs} time(s) each. "
          "Each is a full simulated conversation, so this takes a minute or two…")
    if target == "foreman":
        print("Note: these conversations start real builds, so your latest dashboard will change.")
    # One scenario at a time: the factory holds one brief per machine, and a built agent can move the meeting,
    # so the trip is put back before each agent scenario.
    before_each = None
    if target == "agent":
        from factory.checks.mantle import reset_trip
        before_each = reset_trip
    result = asyncio.run(_evaluate(project, url, [[p] for p in paths], runs, before_each=before_each))
    text, code = summarize(result)
    print(text)
    return code
