"""Production entrypoint for the portal: real key minter, EC2 pool, Caddy sync."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from infra.portal import caddy
from infra.portal.app import create_app
from infra.portal.db import Db
from infra.portal.keys import LiteLLMKeyMinter
from infra.portal.pool import Pool
from infra.portal.providers import provider_from_env

db = Db(Path(os.environ.get("PORTAL_DB", "/data/portal.db")))
minter = LiteLLMKeyMinter(os.environ.get("LITELLM_URL", "http://litellm:4000"), os.environ["LITELLM_MASTER_KEY"],
                          budget_usd=float(os.environ.get("KEY_BUDGET_USD", "5")))
provider = provider_from_env()
pool = Pool(db, provider, warm=int(os.environ.get("WARM", "10")), ceiling=int(os.environ.get("CEILING", "60")),
            domain=os.environ["DOMAIN"], on_change=caddy.push) if provider else None
app = create_app(db=db, minter=minter, pool=pool)


@app.on_event("startup")
async def start_background() -> None:
    try:
        await caddy.push(db.vms("ready"))
    except Exception as e:  # noqa: BLE001 — Caddy may still be starting; the next change pushes again
        print(f"initial caddy push failed: {e}")
    if pool is not None:
        app.state.pool_task = asyncio.create_task(pool.run_forever())
