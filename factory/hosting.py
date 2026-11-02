"""Running what the factory builds: the dashboard on :8600 and a built Mantle agent on :5006."""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

import httpx

REPO = Path(__file__).resolve().parents[1]
WORKSPACE = REPO / "workspace"
LOGS = WORKSPACE / "logs"
PORTS = {"dashboard": 8600, "mantle_agent": 5006}
LATEST = {"dashboard": WORKSPACE / "latest-dashboard", "mantle_agent": WORKSPACE / "latest-agent"}


def dashboard_public_url() -> str:
    return os.environ.get("DASHBOARD_PUBLIC_URL", "http://localhost:8600").rstrip("/") + "/"


def agent_public_url() -> str:
    base = os.environ.get("AGENT_PUBLIC_URL", "http://localhost:5006").rstrip("/")
    return f"{base}/webhooks/inspector/inspect.html?projectUrl={quote(base, safe='')}&channel=inspector"


def free_port(port: int) -> None:
    """Stop whatever is listening on a port (a previous build of the same thing)."""
    try:
        out = subprocess.run(["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"], capture_output=True, text=True).stdout
    except FileNotFoundError:
        out = subprocess.run(["fuser", f"{port}/tcp"], capture_output=True, text=True).stdout
    for pid in out.split():
        try:
            os.kill(int(pid), 15)
        except (ProcessLookupError, ValueError):
            pass


async def wait_http(url: str, timeout_s: float = 90) -> bool:
    deadline = asyncio.get_event_loop().time() + timeout_s
    async with httpx.AsyncClient(timeout=2) as client:
        while asyncio.get_event_loop().time() < deadline:
            try:
                if (await client.get(url)).status_code < 500:
                    return True
            except httpx.HTTPError:
                pass
            await asyncio.sleep(1)
    return False


def _spawn(cmd: list[str], cwd: Path, name: str) -> subprocess.Popen:
    LOGS.mkdir(parents=True, exist_ok=True)
    log = open(LOGS / f"{name}.log", "ab")
    return subprocess.Popen(cmd, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, env=dict(os.environ),
                            start_new_session=True)


class StartFailed(RuntimeError):
    """What was built could not be started — the message goes back to the builder as a problem to fix."""


def train_errors(output: str, limit: int = 1500) -> str:
    """Pull the error lines out of `rasa train` output so a builder can act on them."""
    lines = [ln for ln in output.splitlines() if '"level": "error"' in ln or "ERROR" in ln]
    return ("\n".join(lines) or output[-limit:])[-limit:]


def agent_command(rasa: str, port: int) -> list[str]:
    """Serve a Mantle agent with both the REST channel (for checks) and the Inspector (for people)."""
    return [rasa, "run", "--inspect", "-p", str(port)]


class ArtifactHost:
    async def start(self, kind: str, root: Path) -> str:
        port = PORTS[kind]
        free_port(port)
        await asyncio.sleep(0.5)
        if kind == "dashboard":
            _spawn([sys.executable, "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", str(port)],
                   root, "dashboard")
            ok = await wait_http(f"http://localhost:{port}/api/state", 30)
            url = dashboard_public_url()
        else:
            await self.ensure_dashboard()
            rasa = str(Path(sys.executable).with_name("rasa"))
            trained = subprocess.run([rasa, "train"], cwd=root, capture_output=True, text=True, env=dict(os.environ))
            if trained.returncode != 0:
                raise StartFailed("The agent did not train (`rasa train` failed). Errors:\n"
                                  + train_errors(trained.stdout + trained.stderr))
            _spawn(agent_command(rasa, port), root, "travel-agent")
            ok = await wait_http(f"http://localhost:{port}/", 120)
            url = agent_public_url()
        if not ok:
            log = LOGS / ("dashboard.log" if kind == "dashboard" else "travel-agent.log")
            tail = log.read_text(errors="replace")[-1500:] if log.exists() else ""
            raise StartFailed(f"The {kind.replace('_', ' ')} did not start. Last log lines:\n{tail}")
        return url

    async def ensure_dashboard(self) -> None:
        """The travel agent needs a dashboard to drive: use the latest build, else the checkpoint."""
        if await wait_http("http://localhost:8600/api/state", 1):
            return
        src = LATEST["dashboard"] if LATEST["dashboard"].exists() else REPO / "checkpoints" / "02-dashboard-built" / "dashboard"
        await self.start("dashboard", src)

    async def promote(self, kind: str, root: Path) -> None:
        """Keep a copy of the passing build as the 'latest' one."""
        dest = LATEST[kind]
        if dest.resolve() == Path(root).resolve():
            return
        shutil.rmtree(dest, ignore_errors=True)
        shutil.copytree(root, dest, ignore=shutil.ignore_patterns("__pycache__", ".rasa", "*.png"))
