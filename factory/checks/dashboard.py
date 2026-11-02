"""Probe a running dashboard the way a user would: load it, push data, look again."""
from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
from agents import FunctionTool, function_tool
from playwright.async_api import async_playwright


async def probe(base_url: str, updates: list[dict], shots_dir: Path) -> dict:
    base = base_url.rstrip("/")
    errors: list[str] = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page(viewport={"width": 1180, "height": 820})  # iPad-ish landscape
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))
        await page.goto(base + "/", wait_until="networkidle")
        await page.wait_for_timeout(500)
        before = await page.inner_text("body")
        async with httpx.AsyncClient(timeout=5) as client:
            for u in updates:
                await client.post(f"{base}/api/state", json=u)
        await page.wait_for_timeout(1000)
        after = await page.inner_text("body")
        shot = Path(shots_dir) / f"check-{int(time.time())}.png"
        await page.screenshot(path=str(shot), full_page=True)
        await browser.close()
    return {"console_errors": errors, "text_before": before[:4000], "text_after": after[:4000],
            "screenshot_path": str(shot)}


def probe_dashboard_tool(base_url: str, shots_dir: Path) -> FunctionTool:
    @function_tool
    async def probe_dashboard(updates_json: str) -> str:
        """Load the dashboard in a real browser, send updates, and report what a user sees.

        updates_json: a JSON array of {"panel": "flight"|"weather"|"meeting"|"verdict", "data": {...}} objects.
        Returns page text before and after the updates, any console errors, and a screenshot path."""
        try:
            updates = json.loads(updates_json)
        except json.JSONDecodeError as e:
            return f"updates_json is not valid JSON: {e}"
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(f"{base_url.rstrip('/')}/api/reset")
        return json.dumps(await probe(base_url, updates, shots_dir))

    return probe_dashboard
