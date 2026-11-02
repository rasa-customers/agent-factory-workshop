"""Minting capped LLM keys on the LiteLLM proxy."""
from __future__ import annotations

from typing import Protocol

import httpx


class KeyMinter(Protocol):
    async def mint(self, email: str) -> str: ...
    async def spend(self, key: str) -> float: ...


class LiteLLMKeyMinter:
    def __init__(self, base_url: str, master_key: str, budget_usd: float = 5.0) -> None:
        self.base, self.master, self.budget = base_url.rstrip("/"), master_key, budget_usd

    def _h(self) -> dict:
        return {"Authorization": f"Bearer {self.master}"}

    async def mint(self, email: str) -> str:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(f"{self.base}/key/generate", headers=self._h(),
                             json={"key_alias": email, "max_budget": self.budget,
                                   "metadata": {"workshop": "factory-workshop"}})
            r.raise_for_status()
            return r.json()["key"]

    async def spend(self, key: str) -> float:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{self.base}/key/info", headers=self._h(), params={"key": key})
            if r.status_code != 200:
                return 0.0
            return float((r.json().get("info") or {}).get("spend") or 0.0)
