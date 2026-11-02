"""Labelled link buttons for the latest build ("Watch the build", "Open it").

The Inspector shows a button whose value is a URL as a link button with its title, which reads far
better than a raw URL in the text, and one message can carry several.
"""
from __future__ import annotations

import os

import httpx
from rasa.mantle.tools.buttons import Button
from rasa.mantle.tools.decorator import ToolContext, tool
from rasa.mantle.tools.result import ToolResult


@tool(description="Buttons linking to the latest build's activity page and, once it has passed, the result.")
async def build_links(context: ToolContext) -> ToolResult:
    base = os.environ.get("FACTORY_URL", "http://localhost:8800").rstrip("/")
    async with httpx.AsyncClient(timeout=5) as client:
        links = (await client.get(f"{base}/jobs/latest/links")).json()["links"]
    context.set_buttons([Button(title=link["title"], value=link["url"]) for link in links])
    return ToolResult(llm_response={"count": len(links)})
