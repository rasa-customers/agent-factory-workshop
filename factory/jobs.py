"""Build jobs: what the factory is working on, and everything that happened along the way."""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import AsyncIterator, Literal

JobState = Literal["queued", "building", "checking", "fixing", "passed", "failed"]
Kind = Literal["dashboard", "mantle_agent"]
KINDS: tuple[str, ...] = ("dashboard", "mantle_agent")


@dataclass
class Event:
    ts: float
    actor: Literal["factory", "builder", "checker"]
    text: str


@dataclass
class Job:
    id: str
    kind: Kind
    spec: str
    state: JobState = "queued"
    round: int = 0
    events: list[Event] = field(default_factory=list)
    result_url: str | None = None
    summary: str | None = None
    check_report: list[dict] = field(default_factory=list)
    error: str | None = None


class JobStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._jobs: dict[str, Job] = {}
        self._subs: dict[str, set[asyncio.Queue[Event]]] = {}
        for f in self.root.glob("*.json"):
            d = json.loads(f.read_text())
            d["events"] = [Event(**e) for e in d["events"]]
            job = Job(**d)
            if job.state not in ("passed", "failed"):  # this process can't resume a build another one started
                job.state = "failed"
                job.error = ("The factory restarted while this was building, so the build stopped. "
                             "Ask me to start it again.")
                self._save(job)
            self._jobs[job.id] = job

    def _save(self, job: Job) -> None:
        (self.root / f"{job.id}.json").write_text(json.dumps(asdict(job), indent=1))

    def create(self, kind: Kind, spec: str) -> Job:
        job = Job(id=uuid.uuid4().hex[:8], kind=kind, spec=spec)
        self._jobs[job.id] = job
        self._save(job)
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def add_event(self, job_id: str, actor: str, text: str) -> None:
        job = self._jobs[job_id]
        ev = Event(ts=time.time(), actor=actor, text=text)  # type: ignore[arg-type]
        job.events.append(ev)
        self._save(job)
        for q in self._subs.get(job_id, ()):
            q.put_nowait(ev)

    def update(self, job_id: str, **fields: object) -> None:
        job = self._jobs[job_id]
        for k, v in fields.items():
            setattr(job, k, v)
        self._save(job)
        for q in self._subs.get(job_id, ()):
            q.put_nowait(Event(ts=time.time(), actor="factory", text=f"__state__:{job.state}"))

    async def subscribe(self, job_id: str) -> AsyncIterator[Event]:
        q: asyncio.Queue[Event] = asyncio.Queue()
        self._subs.setdefault(job_id, set()).add(q)
        try:
            for ev in list(self._jobs[job_id].events):
                yield ev
            while True:
                yield await q.get()
        finally:
            self._subs[job_id].discard(q)
