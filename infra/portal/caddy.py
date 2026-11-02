"""The portal host's Caddy config: portal, LLM proxy, and every ready cloud machine.
TLS ends at the load balancer (ACM wildcard cert); Caddy serves plain HTTP and routes by hostname."""
from __future__ import annotations

import os

import httpx

PORTS = {"": 8080, "-foreman": 5005, "-agent": 5006, "-dashboard": 8600, "-factory": 8800}


def render_caddyfile(vms: list[dict], domain: str) -> str:
    blocks = [
        f"http://portal.{domain} {{\n  reverse_proxy portal:8000\n}}",
        f"http://llm.{domain} {{\n  reverse_proxy litellm:4000\n}}",
    ]
    for vm in vms:
        if vm.get("state") != "ready" or not vm.get("ip"):
            continue
        for suffix, port in PORTS.items():
            blocks.append(f"http://{vm['id']}{suffix}.{domain} {{\n  reverse_proxy {vm['ip']}:{port}\n}}")
    health = ":80 {\n  respond /healthz \"ok\" 200\n  respond \"Unknown host\" 404\n}"
    return "{\n  admin 0.0.0.0:2019\n  auto_https off\n}\n\n" + "\n\n".join(blocks + [health]) + "\n"


async def push(vms: list[dict]) -> None:
    """Load a fresh config into the running Caddy (no restart, existing connections survive)."""
    domain = os.environ["DOMAIN"]
    text = render_caddyfile(vms, domain)
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(os.environ.get("CADDY_ADMIN", "http://caddy:2019") + "/load", content=text,
                         headers={"Content-Type": "text/caddyfile"})
        r.raise_for_status()
