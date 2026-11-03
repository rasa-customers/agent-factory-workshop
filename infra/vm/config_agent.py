"""Runs on each cloud machine: waits to be assigned, then configures the workshop for that attendee.

Reads /etc/factory-workshop.env (VM_ID, CONFIG_SECRET, PORTAL_URL, DOMAIN) written by EC2 user-data.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path("/home/workshop/agent-factory-workshop")
CODE_SERVER_CONFIG = Path("/home/workshop/.config/code-server/config.yaml")
EDITOR_SETTINGS = Path("/home/workshop/.local/share/code-server/User/settings.json")
# The workshop's AI lives in the foreman, so the editor's own chat is hidden. The rest keeps the editor quick:
# .venv alone is ~35,000 files, and the marketplace, update and git checks only slow the first load.
EDITOR = {"workbench.startupEditor": "none", "security.workspace.trust.enabled": False,
          "terminal.integrated.cwd": "/home/workshop/agent-factory-workshop",
          "chat.disableAIFeatures": True, "chat.commandCenter.enabled": False,
          "workbench.secondarySideBar.defaultVisibility": "hidden",
          "files.watcherExclude": {"**/.venv/**": True, "**/.git/objects/**": True, "**/__pycache__/**": True,
                                   "**/workspace/**": True},
          "files.exclude": {"**/.venv": True, "**/__pycache__": True, "**/.pytest_cache": True},
          "search.exclude": {"**/.venv": True, "**/workspace/**/models": True},
          "extensions.autoCheckUpdates": False, "extensions.autoUpdate": False,
          "extensions.ignoreRecommendations": True, "update.mode": "none", "telemetry.telemetryLevel": "off",
          "workbench.enableExperiments": False, "git.enabled": False}
SERVICES = {"code": None, "foreman": 5005, "agent": 5006, "dashboard": 8600, "factory": 8800}


def public_urls(vm_id: str, domain: str) -> dict[str, str]:
    return {name: f"https://{vm_id}.{domain}" if name == "code" else f"https://{vm_id}-{name}.{domain}"
            for name in SERVICES}


def render_env(cfg: dict[str, str], vm_id: str, domain: str) -> str:
    urls = public_urls(vm_id, domain)
    values = {k: v for k, v in cfg.items() if v}
    values.update({"FACTORY_PUBLIC_URL": urls["factory"], "DASHBOARD_PUBLIC_URL": urls["dashboard"],
                   "AGENT_PUBLIC_URL": urls["agent"], "FOREMAN_PUBLIC_URL": urls["foreman"]})
    return "".join(f"{k}={v}\n" for k, v in values.items())


def _read_env(path: Path) -> dict[str, str]:
    out = {}
    for line in path.read_text().splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def _fetch(portal: str, vm_id: str, secret: str) -> dict:
    req = urllib.request.Request(f"{portal.rstrip('/')}/internal/vm/{vm_id}/config", headers={"X-Config-Secret": secret})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def apply(cfg: dict, vm_id: str, domain: str) -> None:
    env_file = REPO / ".env"
    env_file.write_text(render_env(cfg["env"], vm_id, domain))
    os.chmod(env_file, 0o600)
    subprocess.run(["chown", "workshop:workshop", str(env_file)])
    cs = CODE_SERVER_CONFIG
    text = f"bind-addr: 0.0.0.0:8080\nauth: password\npassword: {cfg['password']}\ncert: false\n"
    if not cs.exists() or cs.read_text() != text:  # only bounce the editor when its password changes
        cs.parent.mkdir(parents=True, exist_ok=True)
        cs.write_text(text)
        subprocess.run(["chown", "-R", "workshop:workshop", str(cs.parent)])
        subprocess.run(["systemctl", "restart", "code-server@workshop"])
    EDITOR_SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    EDITOR_SETTINGS.write_text(json.dumps(EDITOR, indent=1))  # code-server picks this up without a restart
    subprocess.run(["chown", "-R", "workshop:workshop", str(EDITOR_SETTINGS.parent)])
    # workshop-up may have hit systemd's start limit while the license was missing
    subprocess.run(["systemctl", "reset-failed", "workshop-up"])
    subprocess.run(["systemctl", "restart", "workshop-up"])

def should_reload(source: Path, started_mtime: float, *, assigned: bool) -> bool:
    """A waiting machine keeps pulling new code; restart (systemd brings it back) so it applies the new settings.
    Never once assigned: restarting re-applies the config and restarts the attendee's services."""
    return not assigned and source.stat().st_mtime != started_mtime


def main() -> None:
    conf = _read_env(Path("/etc/factory-workshop.env"))
    vm_id, secret, portal, domain = conf["VM_ID"], conf["CONFIG_SECRET"], conf["PORTAL_URL"], conf["DOMAIN"]
    source = Path(__file__)
    started_mtime = source.stat().st_mtime
    applied = None
    while True:
        if should_reload(source, started_mtime, assigned=applied is not None):
            print("new code pulled while waiting; restarting to pick it up", flush=True)
            sys.exit(0)
        try:
            cfg = _fetch(portal, vm_id, secret)
            if cfg.get("assigned") and cfg != applied:
                apply(cfg, vm_id, domain)
                applied = cfg
        except Exception as e:  # noqa: BLE001 — keep polling through portal restarts
            print(f"config poll failed: {e}", flush=True)
        time.sleep(10)


if __name__ == "__main__":
    main()
