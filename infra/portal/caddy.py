"""The portal host's Caddy config: portal, LLM proxy, and every ready cloud machine, all under one wildcard cert."""
from __future__ import annotations

import os

import httpx

PORTS = {"": 8080, "-foreman": 5005, "-agent": 5006, "-dashboard": 8600, "-factory": 8800}


def render_caddyfile(vms: list[dict], domain: str, cert: str, key: str) -> str:
    tls = f"tls {cert} {key}"
    blocks = [
        f"portal.{domain} {{\n  {tls}\n  reverse_proxy portal:8000\n}}",
        f"llm.{domain} {{\n  {tls}\n  reverse_proxy litellm:4000\n}}",
    ]
    for vm in vms:
        if vm.get("state") != "ready" or not vm.get("ip"):
            continue
        for suffix, port in PORTS.items():
            blocks.append(f"{vm['id']}{suffix}.{domain} {{\n  {tls}\n  reverse_proxy {vm['ip']}:{port}\n}}")
    return "{\n  admin 0.0.0.0:2019\n  auto_https off\n}\n\n" + "\n\n".join(blocks) + "\n"


async def push(vms: list[dict]) -> None:
    """Load a fresh config into the running Caddy (no restart, existing connections survive)."""
    domain = os.environ["DOMAIN"]
    text = render_caddyfile(vms, domain, cert="/certs/fullchain.pem", key="/certs/privkey.pem")
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(os.environ.get("CADDY_ADMIN", "http://caddy:2019") + "/load", content=text,
                         headers={"Content-Type": "text/caddyfile"})
        r.raise_for_status()
