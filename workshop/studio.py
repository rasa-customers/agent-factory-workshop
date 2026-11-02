"""Send conversation events to Rasa Studio, but only where Studio is set up.

Cloud machines get STUDIO_KAFKA_URL from the portal; laptops don't, so their agents publish nothing. (An
agent pointed at a broker it can't reach answers its first message a minute late, so this stays opt-in.)
"""
from __future__ import annotations

import os
from pathlib import Path

TOPIC = "rasa-events"


def event_broker_yaml(env: dict[str, str] | None = None) -> str:
    url = (os.environ if env is None else env).get("STUDIO_KAFKA_URL", "").strip()
    if not url:
        return ""
    return (f"\n# Added by the workshop: conversations go to Rasa Studio.\nevent_broker:\n  type: kafka\n"
            f"  url: {url}\n  topic: {TOPIC}\n  partition_by_sender: true\n  security_protocol: PLAINTEXT\n")


def write_integrations(project: Path, env: dict[str, str] | None = None) -> None:
    """integrations.yml = the tracked integrations.base.yml, plus Studio when it is set up."""
    project = Path(project)
    base = (project / "integrations.base.yml").read_text()
    (project / "integrations.yml").write_text(base + event_broker_yaml(env))


def add_event_broker(project: Path, env: dict[str, str] | None = None) -> None:
    """Add Studio to a built agent's integrations.yml, once."""
    path = Path(project) / "integrations.yml"
    text = path.read_text()
    extra = event_broker_yaml(env)
    if extra and "event_broker:" not in text:
        path.write_text(text.rstrip("\n") + "\n" + extra)
