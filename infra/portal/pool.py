"""The cloud machine pool: keep N idle machines warm, never exceed the ceiling, hand them out once."""
from __future__ import annotations

import asyncio
import secrets
import time

from infra.portal.db import Db
from infra.portal.providers import VmProvider

ACTIVE = ("launching", "ready")


class Pool:
    def __init__(self, db: Db, provider: VmProvider, *, warm: int = 10, ceiling: int = 60,
                 domain: str = "factory-workshop.playground-cse.rasa-dev.io", on_change=None) -> None:
        self.db, self.provider, self.warm, self.ceiling, self.domain = db, provider, warm, ceiling, domain
        self.on_change = on_change  # called with the VM list whenever a machine becomes reachable
        self.lock = asyncio.Lock()

    def _active(self) -> list[dict]:
        return self.db.vms(*ACTIVE)

    def _idle(self) -> list[dict]:
        return [v for v in self._active() if not v["attendee_email"]]

    async def _launch(self) -> dict | None:
        if len(self._active()) >= self.ceiling:
            return None
        n = len(self.db.vms()) + 1
        vm_id = f"vm-{n:02d}"
        hostname = f"{vm_id}.{self.domain}"
        secret = secrets.token_urlsafe(24)
        self.db.add_vm(id=vm_id, hostname=hostname, state="launching", config_secret=secret,
                       password=secrets.token_urlsafe(9), created_at=time.time())
        instance_id = await self.provider.launch(vm_id, hostname, secret)
        self.db.set_vm(vm_id, instance_id=instance_id)
        return self.db.vm(vm_id)

    async def tick(self) -> None:
        async with self.lock:
            changed = False
            for vm in self.db.vms("launching"):
                ip = await self.provider.is_ready(vm)
                if ip:
                    self.db.set_vm(vm["id"], state="ready", ip=ip, ready_at=time.time())
                    changed = True
            if changed and self.on_change:
                await self.on_change(self.db.vms("ready"))
            while len(self._idle()) < self.warm:
                if await self._launch() is None:
                    break

    async def scale(self, n: int) -> None:
        async with self.lock:
            for _ in range(max(0, n)):
                if await self._launch() is None:
                    break

    async def assign(self, email: str) -> dict | None:
        async with self.lock:
            a = self.db.attendee(email)
            if a and a["vm_id"]:
                return self.db.vm(a["vm_id"])
            idle = self._idle()
            vm = next((v for v in idle if v["state"] == "ready"), None) or (idle[0] if idle else None)
            if vm is None:
                vm = await self._launch()
            if vm is None:
                return None
            self.db.set_vm(vm["id"], attendee_email=email)
            self.db.set_attendee(email, vm_id=vm["id"])
            return self.db.vm(vm["id"])

    async def status_for(self, email: str) -> dict:
        a = self.db.attendee(email)
        vm = self.db.vm(a["vm_id"]) if a else None
        if vm is None:
            vm = await self.assign(email) if a and a["choice"] == "cloud" else None
        if vm is None:
            return {"state": "full"}
        if vm["state"] != "ready":
            return {"state": "starting"}
        return {"state": "ready", "url": f"https://{vm['hostname']}/", "password": vm["password"],
                "foreman_url": f"https://{vm['id']}-foreman.{self.domain}/webhooks/inspector/inspect.html"
                               f"?projectUrl=https%3A%2F%2F{vm['id']}-foreman.{self.domain}&channel=inspector"}

    async def run_forever(self, every_s: float = 15) -> None:
        while True:
            try:
                await self.tick()
            except Exception as e:  # noqa: BLE001 — keep the pool loop alive through AWS hiccups
                print(f"pool tick failed: {e}")
            await asyncio.sleep(every_s)
