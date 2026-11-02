import json

import pytest

from factory.jobs import JobStore


@pytest.fixture
def store(tmp_path):
    return JobStore(tmp_path / "jobs")


async def call_tool(server, name, args):
    result = await server.call_tool(name, args)
    content, structured = result if isinstance(result, tuple) else (result, None)
    if structured is not None:
        return structured.get("result", structured)
    return json.loads(content[0].text)
