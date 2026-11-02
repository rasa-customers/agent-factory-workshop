"""Probe a running dashboard the way a user would: load it, push data, look again."""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import httpx
from agents import FunctionTool, function_tool
from playwright.async_api import async_playwright


VIEWPORTS = {"tablet": (1180, 820), "phone": (390, 844), "projector": (1920, 1080)}

# What a person would notice at a glance: colours, the biggest text, and whether the page spills sideways.
LOOK_JS = """() => {
  const bg = el => getComputedStyle(el).backgroundColor;
  const clear = c => c === 'rgba(0, 0, 0, 0)' || c === 'transparent';
  const seen = new Set(), texts = [];
  for (const el of document.body.querySelectorAll('*')) {
    const own = [...el.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join(' ').trim();
    const r = el.getBoundingClientRect();
    if (!own || r.width === 0 || r.height === 0 || seen.has(own)) continue;
    seen.add(own);
    const cs = getComputedStyle(el);
    texts.push({text: own.slice(0, 60), font_px: parseFloat(cs.fontSize), weight: cs.fontWeight, color: cs.color});
  }
  texts.sort((a, b) => b.font_px - a.font_px);
  let back = null;  // what is painted behind the middle of the screen, wherever the page puts it
  for (let el = document.elementFromPoint(innerWidth / 2, innerHeight / 2); el; el = el.parentElement) {
    if (!clear(bg(el))) { back = bg(el); break; }
  }
  if (!back) back = clear(bg(document.documentElement)) ? 'rgb(255, 255, 255)' : bg(document.documentElement);
  return {page_background: back,
          body_text_color: getComputedStyle(document.body).color,
          largest_text: texts.slice(0, 8),
          horizontal_overflow: document.documentElement.scrollWidth > window.innerWidth + 1,
          map: {present: !!document.querySelector('.leaflet-container'),
                tiles_loaded: document.querySelectorAll('img.leaflet-tile-loaded').length,
                markers: document.querySelectorAll('.leaflet-marker-icon').length
                         + document.querySelectorAll('.leaflet-overlay-pane path.leaflet-interactive[d*="a"]').length,
                lines: [...document.querySelectorAll('.leaflet-overlay-pane path')].filter(e => !/a/i.test(e.getAttribute('d') || '')).length}};
}"""


_LOCKS: dict[str, asyncio.Lock] = {}


# A fingerprint of how every element looks, to spot highlights that come and go after an update.
STYLE_JS = """() => [...document.body.querySelectorAll('*')].map((el, i) => {
  const cs = getComputedStyle(el);
  return [i + ':' + el.tagName, (el.innerText || '').trim().slice(0, 60),
          [el.className, cs.animationName, cs.backgroundColor, cs.boxShadow, cs.outlineStyle, cs.outlineColor,
           cs.borderColor, cs.color, cs.transform, cs.opacity].join('|')];
})"""


# Started just before the updates: records every CSS/Web animation or transition that runs in the next 2 s.
WATCH_ANIMATIONS_JS = """() => {
  window.__animSeen = []; const seen = new Set(); const t0 = performance.now();
  const id = setInterval(() => {
    for (const a of document.getAnimations()) {
      const el = a.effect && a.effect.target; if (!el) continue;
      const what = a.animationName || a.transitionProperty || 'animation';
      const text = (el.innerText || el.textContent || '').trim().slice(0, 60);
      const key = what + '|' + text; if (seen.has(key)) continue; seen.add(key);
      window.__animSeen.push({text: text, what: what});
    }
    if (performance.now() - t0 > 2000) clearInterval(id);
  }, 40);
}"""


def briefly_changed(soon: list, later: list, limit: int = 8) -> list[dict]:
    """Elements whose look right after an update differs from a few seconds later: a highlight."""
    later_by_key = {k: sig for k, _, sig in later}
    out, seen = [], set()
    for key, text, sig in soon:
        if key in later_by_key and later_by_key[key] != sig and text and text not in seen:
            seen.add(text)
            out.append({"text": text})
    return out[:limit]


async def probe(base_url: str, updates: list[dict], shots_dir: Path, viewport: str = "tablet") -> dict:
    """One probe at a time per dashboard: the dashboard holds one shared state, and the checker's model
    happily calls the tool several times in parallel."""
    base = base_url.rstrip("/")
    async with _LOCKS.setdefault(base, asyncio.Lock()):
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(f"{base}/api/reset")
        return await _probe(base, updates, shots_dir, viewport)


async def _probe(base: str, updates: list[dict], shots_dir: Path, viewport: str) -> dict:
    errors: list[str] = []
    width, height = VIEWPORTS.get(viewport, VIEWPORTS["tablet"])
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page(viewport={"width": width, "height": height})
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))
        await page.goto(base + "/", wait_until="networkidle")
        await page.wait_for_timeout(500)
        before = await page.inner_text("body")
        await page.evaluate(WATCH_ANIMATIONS_JS)
        async with httpx.AsyncClient(timeout=5) as client:
            for u in updates:
                await client.post(f"{base}/api/state", json=u)
        await page.wait_for_timeout(300)
        soon = await page.evaluate(STYLE_JS)
        await page.wait_for_timeout(2700)
        later = await page.evaluate(STYLE_JS)
        after = await page.inner_text("body")
        look = await page.evaluate(LOOK_JS)
        look["highlighted_briefly"] = briefly_changed(soon, later) if updates else []
        look["animated"] = (await page.evaluate("window.__animSeen || []"))[:8] if updates else []
        look["viewport"] = f"{viewport if viewport in VIEWPORTS else 'tablet'} {width}x{height}"
        shot = Path(shots_dir) / f"check-{time.time_ns()}.png"
        await page.screenshot(path=str(shot), full_page=True)
        await browser.close()
    return {"console_errors": errors, "text_before": before[:4000], "text_after": after[:4000],
            "look": look, "screenshot_path": str(shot)}


def probe_dashboard_tool(base_url: str, shots_dir: Path) -> FunctionTool:
    @function_tool
    async def probe_dashboard(updates_json: str, viewport: str = "tablet") -> str:
        """Load the dashboard in a real browser, send updates, and report what a user sees.

        updates_json: a JSON array of {"panel": "flight"|"weather"|"meeting"|"verdict", "data": {...}} objects.
        viewport: "tablet" (1180x820, the default), "phone" (390x844) or "projector" (1920x1080).
        Returns page text before and after the updates, any console errors, and `look` after the updates:
        page background and text colours, the largest text on the page (text, font size, weight, colour),
        whether the page overflows sideways, `highlighted_briefly`: elements that looked different just
        after the update than a few seconds later (a highlight on change), `animated`: elements that ran a CSS
        animation or transition in the 2 s after the update (with which property), and `map`: whether a map is on
        the page, how many map tiles loaded, and how many markers and lines are drawn on it."""
        try:
            updates = json.loads(updates_json)
        except json.JSONDecodeError as e:
            return f"updates_json is not valid JSON: {e}"
        return json.dumps(await probe(base_url, updates, shots_dir, viewport))

    return probe_dashboard
