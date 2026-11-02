"""The cloud machine pool: keep N idle machines warm, never exceed the ceiling, hand them out once."""
from __future__ import annotations

import asyncio
import secrets
import time

from infra.portal.db import Db
from infra.portal.providers import VmProvider

ACTIVE = ("launching", "ready")
REPO_DIR = "/home/workshop/agent-factory-workshop"


class Pool:
    def __init__(self, db: Db, provider: VmProvider, *, warm: int = 10, ceiling: int = 60,
                 domain: str = "factory-workshop.playground-cse.rasa-dev.io", on_change=None) -> None:
        self.db, self.provider, self.warm, self.ceiling, self.domain = db, provider, warm, ceiling, domain
        self.on_change = on_change  # called with the VM list whenever a machine becomes reachable
        self.lock = asyncio.Lock()
        self._retry_after = 0.0
        self._pushed = True

    def _active(self) -> list[dict]:
        return self.db.vms(*ACTIVE)

    def _idle(self) -> list[dict]:
        return [v for v in self._active() if not v["attendee_email"]]

    def _reserve(self) -> dict | None:
        """Claim a machine record (call under the lock). The slow EC2 call happens later, outside it."""
        if len(self._active()) >= self.ceiling or time.time() < self._retry_after:
            return None
        vm_id = f"vm-{secrets.token_hex(4)}"  # unguessable: machine URLs are the only thing keeping attendees apart
        self.db.add_vm(id=vm_id, hostname=f"{vm_id}.{self.domain}", state="launching",
                       config_secret=secrets.token_urlsafe(24), password=secrets.token_urlsafe(9),
                       created_at=time.time())
        return self.db.vm(vm_id)

    async def _start(self, vm: dict) -> dict | None:
        try:
            instance_id = await self.provider.launch(vm["id"], vm["hostname"], vm["config_secret"])
        except Exception as e:  # noqa: BLE001 — a failed launch must not poison the pool
            print(f"launch of {vm['id']} failed: {e}", flush=True)
            self.db.set_vm(vm["id"], state="failed")
            self._retry_after = time.time() + 60  # don't hammer EC2 (or fill the table) while something is wrong
            return None
        self.db.set_vm(vm["id"], instance_id=instance_id)
        return self.db.vm(vm["id"])

    async def _launch(self) -> dict | None:
        async with self.lock:
            vm = self._reserve()
        return await self._start(vm) if vm else None

    async def _check(self, vm: dict) -> bool:
        try:
            ip = await self.provider.is_ready(vm)
        except Exception as e:  # noqa: BLE001
            print(f"readiness check for {vm['id']} failed: {e}", flush=True)
            return False
        if ip:
            self.db.set_vm(vm["id"], state="ready", ip=ip, ready_at=time.time())
        return bool(ip)

    async def tick(self) -> None:
        # health checks run side by side and outside the lock, so sign-ups never wait on EC2
        launching = [v for v in self.db.vms("launching") if v["instance_id"]]
        became_ready = any(await asyncio.gather(*(self._check(v) for v in launching)))
        if (became_ready or not self._pushed) and self.on_change:
            try:
                await self.on_change(self.db.vms("ready"))
                self._pushed = True
            except Exception as e:  # noqa: BLE001 — retried next tick
                print(f"router update failed: {e}", flush=True)
                self._pushed = False
        async with self.lock:
            fresh = []
            while len(self._idle()) < self.warm and (vm := self._reserve()):
                fresh.append(vm)
        await asyncio.gather(*(self._start(v) for v in fresh))

    async def scale(self, n: int) -> None:
        async with self.lock:
            fresh = [vm for _ in range(max(0, n)) if (vm := self._reserve())]
        await asyncio.gather(*(self._start(v) for v in fresh))

    async def assign(self, email: str) -> dict | None:
        async with self.lock:
            a = self.db.attendee(email)
            if a and a["vm_id"]:
                return self.db.vm(a["vm_id"])
            idle = self._idle()
            vm = next((v for v in idle if v["state"] == "ready"), None) or (idle[0] if idle else None)
            new = vm is None
            if new:
                vm = self._reserve()
            if vm is None:
                return None
            self.db.set_vm(vm["id"], attendee_email=email)
            self.db.set_attendee(email, vm_id=vm["id"])
        if new and await self._start(vm) is None:
            self.db.set_attendee(email, vm_id=None)  # launch failed: let them get the next machine
            return None
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
        try:
            foreman_up = bool(await self.provider.services_up(vm))
        except Exception:  # noqa: BLE001
            foreman_up = False
        return {"state": "ready", "url": f"https://{vm['hostname']}/?folder={REPO_DIR}", "password": vm["password"],
                "license": bool(a and a["license"]), "foreman_up": foreman_up,
                "foreman_url": f"https://{vm['id']}-foreman.{self.domain}/webhooks/inspector/inspect.html"
                               f"?projectUrl=https%3A%2F%2F{vm['id']}-foreman.{self.domain}&channel=inspector"}

    async def run_forever(self, every_s: float = 15) -> None:
        while True:
            try:
                await self.tick()
            except Exception as e:  # noqa: BLE001 — keep the pool loop alive through AWS hiccups
                print(f"pool tick failed: {e}")
            await asyncio.sleep(every_s)
