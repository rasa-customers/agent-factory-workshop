import json

import pytest

from factory.jobs import JobStore


@pytest.fixture
def store(tmp_path):
    return JobStore(tmp_path / "jobs")


async def call_tool(server, name, args):
    """A tool's result, or {"error", "is_error": True} when the tool failed (which Mantle sees as is_error)."""
    from mcp.server.fastmcp.exceptions import ToolError
    try:
        result = await server.call_tool(name, args)
    except ToolError as e:
        return {"error": str(e), "is_error": True}
    content, structured = result if isinstance(result, tuple) else (result, None)
    if structured is not None:
        return structured.get("result", structured)
    return json.loads(content[0].text)


async def build(server, kind, brief):
    """What the foreman does: save the agreed brief, then (once the person says yes) start it."""
    await call_tool(server, "save_brief", {"kind": kind, "brief": brief})
    return await call_tool(server, "start_build", {})
