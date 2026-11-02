"""Start and stop the workshop's local services, and jump to known-good checkpoints."""
from __future__ import annotations

import asyncio
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote

from workshop.env import check_settings, export_settings, load_settings

REPO = Path(__file__).resolve().parents[1]
WORKSPACE = REPO / "workspace"
LOGS = WORKSPACE / "logs"
CHECKPOINTS = {
    "02-dashboard-built": ("dashboard", "dashboard", "latest-dashboard"),
    "02b-dashboard-extended": ("dashboard", "dashboard", "latest-dashboard"),
    "03-agent-built": ("mantle_agent", "travel-agent", "latest-agent"),
    "03b-agent-extended": ("mantle_agent", "travel-agent", "latest-agent"),
}


def install_checkpoint(name: str, repo: Path = REPO, workspace: Path = WORKSPACE) -> tuple[str, Path]:
    if name not in CHECKPOINTS:
        raise SystemExit(f"Unknown checkpoint {name!r}. Valid checkpoints: {', '.join(CHECKPOINTS)}")
    kind, sub, latest = CHECKPOINTS[name]
    dest = Path(workspace) / latest
    shutil.rmtree(dest, ignore_errors=True)
    shutil.copytree(Path(repo) / "checkpoints" / name / sub, dest,
                    ignore=shutil.ignore_patterns("__pycache__", "models", ".rasa"))
    return kind, dest


def _export_settings() -> None:
    export_settings()


def inspector_url(base: str) -> str:
    base = base.rstrip("/")
    return f"{base}/webhooks/inspector/inspect.html?projectUrl={quote(base, safe='')}&channel=inspector"


def checkpoint(name: str) -> int:
    _export_settings()
    from factory.hosting import ArtifactHost

    kind, dest = install_checkpoint(name)
    print(f"Installed checkpoint {name} → {dest.relative_to(REPO)}; starting it…")
    url = asyncio.run(ArtifactHost().start(kind, dest))
    if kind == "dashboard":
        from factory.example_data import seed_dashboard
        asyncio.run(seed_dashboard("http://localhost:8600"))
    print(f"Ready: {url}")
    return 0


def _spawn(name: str, cmd: list[str], cwd: Path = REPO) -> subprocess.Popen:
    LOGS.mkdir(parents=True, exist_ok=True)
    log = open(LOGS / f"{name}.log", "ab")
    return subprocess.Popen(cmd, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, env=dict(os.environ),
                            start_new_session=True)


def up() -> int:
    problems = check_settings(load_settings())
    if problems:
        print("Fix these first (edit .env), then run `workshop up` again:")
        for p in problems:
            print(f"  ✗ {p}")
        return 1
    _export_settings()
    from factory.hosting import agent_command, free_port, wait_http

    py = sys.executable
    rasa = str(Path(py).with_name("rasa"))
    for port in (5005, 8600, 8700, 8800):
        free_port(port)
    time.sleep(0.5)

    dash_dir = WORKSPACE / "latest-dashboard"
    if not dash_dir.exists():
        dash_dir = REPO / "templates" / "dashboard"
    from workshop.studio import write_integrations
    write_integrations(REPO / "foreman")
    print("Training the foreman (first run takes a few seconds)…")
    subprocess.run([rasa, "train"], cwd=REPO / "foreman", capture_output=True, env=dict(os.environ))

    procs = [
        _spawn("travel-mcp", [py, "-m", "travel_mcp.server"]),
        _spawn("factory", [py, "-m", "factory.server"]),
        _spawn("dashboard", [py, "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8600"], cwd=dash_dir),
        _spawn("foreman", agent_command(rasa, 5005), cwd=REPO / "foreman"),
    ]
    print("Starting the factory, the travel tools, the dashboard and the foreman…")
    checks = {"travel tools": "http://localhost:8700/mcp/", "factory": "http://localhost:8800/jobs/none",
              "dashboard": "http://localhost:8600/api/state", "foreman": "http://localhost:5005/"}
    for name, url in checks.items():
        ok = asyncio.run(wait_http(url, 120))
        print(f"  {'✓' if ok else '✗'} {name}" + ("" if ok else f" — see workspace/logs/"))

    foreman = os.environ.get("FOREMAN_PUBLIC_URL", "http://localhost:5005")
    dashboard = os.environ.get("DASHBOARD_PUBLIC_URL", "http://localhost:8600")
    print(f"""
┌──────────────────────────────────────────────────────────────────────
│  Talk to the foreman:   {inspector_url(foreman)}
│  Dashboard:             {dashboard.rstrip('/')}/
│  Build activity:        the foreman gives you a link when a build starts
│  Logs:                  workspace/logs/
│  Stop everything:       Ctrl-C
└──────────────────────────────────────────────────────────────────────""")
    code = 0
    try:
        code = watch([procs[0], procs[1], procs[3]])  # the factory replaces the dashboard process when it builds one
    except KeyboardInterrupt:
        print("\nStopping…")
    finally:
        for p in procs:
            try:
                os.killpg(p.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        for port in (5006,):
            free_port(port)
    return code


def watch(procs: list) -> int:
    """Wait while every watched service runs; 1 if one stops (so systemd restarts the stack)."""
    while all(p.poll() is None for p in procs):
        time.sleep(1)
    print("A service stopped unexpectedly — check workspace/logs/.")
    return 1
