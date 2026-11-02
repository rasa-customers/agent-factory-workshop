"""A spec is the person's brief plus the factory's fixed contract for that kind of build.

The brief is what people shape with the foreman (look, tone, emphasis, extras). The contract is what other
parts of the workshop rely on (the dashboard's data API, the travel tools), so it is never left to chance.
"""
from __future__ import annotations

from pathlib import Path

CONTRACTS = {kind: (Path(__file__).with_name("contracts") / f"{kind}.md").read_text().strip()
             for kind in ("dashboard", "mantle_agent")}


def full_spec(kind: str, brief: str) -> str:
    brief = brief.strip()
    contract = CONTRACTS[kind]
    if contract in brief:
        return brief
    return f"{brief}\n\n{contract}"


def revised_brief(brief: str, change: str) -> str:
    """The brief after a change someone asked for once they had seen a finished build."""
    marker = "## Changes asked for after seeing it"
    if marker not in brief:
        brief = f"{brief.strip()}\n\n{marker}"
    return f"{brief}\n\n- {change.strip()}"
