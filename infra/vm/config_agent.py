"""Runs on each cloud machine: waits to be assigned, then configures the workshop for that attendee.

Reads /etc/factory-workshop.env (VM_ID, CONFIG_SECRET, PORTAL_URL, DOMAIN) written by EC2 user-data.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path

REPO = Path("/home/workshop/agent-factory-workshop")
CODE_SERVER_CONFIG = Path("/home/workshop/.config/code-server/config.yaml")
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
    # workshop-up may have hit systemd's start limit while the license was missing
    subprocess.run(["systemctl", "reset-failed", "workshop-up"])
    subprocess.run(["systemctl", "restart", "workshop-up"])

def main() -> None:
    conf = _read_env(Path("/etc/factory-workshop.env"))
    vm_id, secret, portal, domain = conf["VM_ID"], conf["CONFIG_SECRET"], conf["PORTAL_URL"], conf["DOMAIN"]
    applied = None
    while True:
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
