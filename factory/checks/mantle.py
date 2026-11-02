"""Checking a built Mantle agent: talk to it through rasa-tools, and confirm the dashboard moved."""
from __future__ import annotations

import httpx

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from agents import FunctionTool, function_tool
from agents.mcp import MCPServerStdio, MCPServerStreamableHttp, create_static_tool_filter
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

TRAVEL_MCP_URL = os.environ.get("TRAVEL_MCP_URL", "http://localhost:8700/mcp/")


def rasa_tools_server(project: Path, rasa_server_url: str, tool_names: list[str] | None = None) -> MCPServerStdio:
    """The Rasa Copilot MCP server over stdio. env must be passed through or it can't see RASA_LICENSE."""
    return MCPServerStdio(
        name="rasa-tools",
        params={"command": sys.executable,
                "args": ["-m", "rasa", "tools", "run", "--mode", "stdio", "--project-path", str(project),
                         "--rasa-server-url", rasa_server_url],
                "env": dict(os.environ), "cwd": str(project)},
        client_session_timeout_seconds=600,
        cache_tools_list=True,
        tool_filter=create_static_tool_filter(allowed_tool_names=tool_names) if tool_names else None,
    )


def train_project(root: Path, run=subprocess.run) -> str:
    """Validate and train the Mantle project; return OK or the real error lines.
    (Used instead of rasa-tools' train tool, which hides skill-load errors in stdio mode.)"""
    from factory.hosting import train_errors
    rasa = str(Path(sys.executable).with_name("rasa"))
    r = run([rasa, "train"], cwd=root, capture_output=True, text=True, env=dict(os.environ), timeout=300)
    if r.returncode == 0:
        return "OK — the project validated and trained."
    return "FAILED — fix these and train again:\n" + train_errors((r.stdout or "") + (r.stderr or ""))


def train_project_tool(root: Path) -> FunctionTool:
    @function_tool(name_override="train_project")
    async def _train() -> str:
        """Validate and train this Mantle project. Returns OK, or the exact errors to fix."""
        import asyncio
        return await asyncio.to_thread(train_project, root)
    return _train


TRUTH_TOOLS = ["get_flight", "get_meeting", "get_weather", "estimate_travel_minutes", "find_alternate_flights",
               "available_meeting_times"]


async def reset_trip(url: str = TRAVEL_MCP_URL) -> None:
    """Put the trip back (meeting time and all) so one check's reschedule can't leak into the next."""
    base = url.rsplit("/mcp", 1)[0]
    async with httpx.AsyncClient(timeout=5) as client:
        (await client.post(f"{base}/reset")).raise_for_status()


def travel_truth_server(url: str = TRAVEL_MCP_URL) -> MCPServerStreamableHttp:
    """The checker's read-only view of the travel data, so it can tell tool facts from invented ones."""
    return MCPServerStreamableHttp(params={"url": url}, name="travel-truth",
                                   tool_filter=create_static_tool_filter(allowed_tool_names=TRUTH_TOOLS),
                                   client_session_timeout_seconds=30)


def updates_since(history: list[dict], ts: float) -> list[dict]:
    return [h for h in history if h["ts"] >= ts]


async def fetch_dashboard_history(url: str = TRAVEL_MCP_URL) -> list[dict]:
    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            res = await session.call_tool("get_dashboard_history", {})
    if res.structuredContent is not None:
        return res.structuredContent.get("result", [])
    return json.loads(res.content[0].text) if res.content else []


def dashboard_history_tool(started_at: float | None = None) -> FunctionTool:
    t0 = started_at or time.time()

    @function_tool
    async def dashboard_updates_since_check_started() -> str:
        """List every dashboard update the agent sent since this check started (panel, data, ok)."""
        return json.dumps(updates_since(await fetch_dashboard_history(), t0))

    return dashboard_updates_since_check_started
