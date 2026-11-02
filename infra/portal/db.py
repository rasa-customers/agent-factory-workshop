"""SQLite storage for the portal: attendees and cloud machines."""
from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS attendees (
  email TEXT PRIMARY KEY, created_at REAL, llm_key TEXT, license TEXT, choice TEXT,
  vm_id TEXT, session_token TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS vms (
  id TEXT PRIMARY KEY, instance_id TEXT, hostname TEXT, ip TEXT, state TEXT, attendee_email TEXT,
  config_secret TEXT, password TEXT, created_at REAL, ready_at REAL);
"""


class Db:
    def __init__(self, path: Path) -> None:
        self.conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.lock = threading.Lock()

    def q(self, sql: str, *args: Any) -> list[dict]:
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    def one(self, sql: str, *args: Any) -> dict | None:
        rows = self.q(sql, *args)
        return rows[0] if rows else None

    # attendees
    def attendee(self, email: str) -> dict | None:
        return self.one("SELECT * FROM attendees WHERE email=?", email)

    def attendee_by_session(self, token: str | None) -> dict | None:
        return self.one("SELECT * FROM attendees WHERE session_token=?", token) if token else None

    def add_attendee(self, email: str, llm_key: str, token: str) -> None:
        self.q("INSERT INTO attendees(email, created_at, llm_key, session_token) VALUES (?,?,?,?)",
               email, time.time(), llm_key, token)

    def set_attendee(self, email: str, **fields: Any) -> None:
        cols = ", ".join(f"{k}=?" for k in fields)
        self.q(f"UPDATE attendees SET {cols} WHERE email=?", *fields.values(), email)

    def attendees(self) -> list[dict]:
        return self.q("SELECT * FROM attendees ORDER BY created_at")

    # vms
    def add_vm(self, **fields: Any) -> None:
        cols = ", ".join(fields)
        self.q(f"INSERT INTO vms({cols}) VALUES ({', '.join('?' * len(fields))})", *fields.values())

    def set_vm(self, vm_id: str, **fields: Any) -> None:
        cols = ", ".join(f"{k}=?" for k in fields)
        self.q(f"UPDATE vms SET {cols} WHERE id=?", *fields.values(), vm_id)

    def vm(self, vm_id: str | None) -> dict | None:
        return self.one("SELECT * FROM vms WHERE id=?", vm_id) if vm_id else None

    def vms(self, *states: str) -> list[dict]:
        if not states:
            return self.q("SELECT * FROM vms ORDER BY created_at")
        return self.q(f"SELECT * FROM vms WHERE state IN ({', '.join('?' * len(states))}) ORDER BY created_at", *states)
