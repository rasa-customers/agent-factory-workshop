import json

import pytest

from travel_mcp import server


async def _call(name, args):
    result = await server.mcp.call_tool(name, args)
    # FastMCP returns (content_blocks, structured) in mcp>=1.10
    content, structured = result if isinstance(result, tuple) else (result, None)
    if structured is not None:
        return structured.get("result", structured)
    return json.loads(content[0].text)


@pytest.fixture
def call():
    from travel_mcp import weather
    server.DASHBOARD_HISTORY.clear()
    weather.FORECASTS.clear()
    return _call
