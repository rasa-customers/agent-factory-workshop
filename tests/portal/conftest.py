import pytest
from fastapi.testclient import TestClient

from infra.portal.app import create_app
from infra.portal.db import Db


class FakeMinter:
    def __init__(self):
        self.calls = 0

    async def mint(self, email):
        self.calls += 1
        return f"sk-fake-{self.calls}"

    async def spend(self, key):
        return 0.42


@pytest.fixture
def minter():
    return FakeMinter()


@pytest.fixture
def db(tmp_path):
    return Db(tmp_path / "portal.db")


@pytest.fixture
def client(db, minter, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "pw")
    monkeypatch.setenv("REPO_URL", "https://github.com/RasaHQ/agent-factory-workshop")
    monkeypatch.setenv("PROXY_BASE_URL", "https://llm.example/v1")
    monkeypatch.setenv("RASA_LICENSE_URL", "https://rasa.example/license")
    app = create_app(db=db, minter=minter, pool=None)
    return TestClient(app)
