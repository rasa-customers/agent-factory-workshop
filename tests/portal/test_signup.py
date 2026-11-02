def signup(client, email="ada@example.com"):
    return client.post("/signup", data={"email": email}, follow_redirects=False)


def test_signup_mints_key_and_sets_cookie(client):
    r = signup(client)
    assert r.status_code == 303 and r.headers["location"] == "/me"
    assert "session" in r.cookies
    page = client.get("/me").text
    assert "sk-fake-1" in page and "https://llm.example/v1" in page


def test_signup_is_idempotent_on_normalized_email(client, minter):
    signup(client, " Ada@Example.com ")
    client.cookies.clear()
    signup(client, "ada@example.com")
    assert minter.calls == 1
    assert "sk-fake-1" in client.get("/me").text


def test_signup_rejects_non_email(client):
    r = signup(client, "not an email")
    assert r.status_code == 400


def test_me_without_session_redirects_home(client):
    r = client.get("/me", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"


def test_me_links_license_signup(client):
    signup(client)
    assert "https://rasa.example/license" in client.get("/me").text


def test_local_choice_shows_prefilled_command(client):
    signup(client)
    client.post("/license", data={"license": "LIC-123"})
    client.post("/choose", data={"choice": "local"})
    page = client.get("/me").text
    assert "git clone https://github.com/RasaHQ/agent-factory-workshop" in page
    assert "--llm-key sk-fake-1" in page and "--license LIC-123" in page
    assert "--base-url https://llm.example/v1" in page


def test_admin_requires_password(client):
    assert client.get("/admin").status_code == 401
    assert client.get("/admin", auth=("admin", "pw")).status_code == 200


def test_admin_shows_counts(client):
    signup(client)
    client.post("/choose", data={"choice": "local"})
    page = client.get("/admin", auth=("admin", "pw")).text
    assert "1 signed up" in page and "1 local" in page


def test_event_code_required_when_set(db, minter, monkeypatch):
    from fastapi.testclient import TestClient
    from infra.portal.app import create_app
    monkeypatch.setenv("EVENT_CODE", "nyc26")
    c = TestClient(create_app(db=db, minter=minter, pool=None))
    assert "nyc26" not in c.get("/").text                      # the code isn't leaked by the page itself
    assert 'value="nyc26"' in c.get("/?code=nyc26").text        # the QR/link pre-fills it
    r = c.post("/signup", data={"email": "a@x.io"}, follow_redirects=False)
    assert r.status_code == 403 and minter.calls == 0
    r = c.post("/signup", data={"email": "a@x.io", "code": "NYC26 "}, follow_redirects=False)
    assert r.status_code == 303 and minter.calls == 1


def test_signup_cap_blocks_new_emails_but_not_returning_ones(db, minter, monkeypatch):
    from fastapi.testclient import TestClient
    from infra.portal.app import create_app
    monkeypatch.setenv("SIGNUP_CAP", "1")
    c = TestClient(create_app(db=db, minter=minter, pool=None))
    assert c.post("/signup", data={"email": "a@x.io"}, follow_redirects=False).status_code == 303
    r = c.post("/signup", data={"email": "b@x.io"}, follow_redirects=False)
    assert r.status_code == 403 and "Rasa person" in r.text and minter.calls == 1
    assert c.post("/signup", data={"email": "A@x.io"}, follow_redirects=False).status_code == 303


async def test_double_submit_mints_one_key(db, monkeypatch):
    import asyncio
    import httpx
    from infra.portal.app import create_app

    class SlowMinter:
        calls = 0
        async def mint(self, email):
            SlowMinter.calls += 1
            await asyncio.sleep(0.05)
            return f"sk-{SlowMinter.calls}"
        async def spend(self, key):
            return 0.0

    app = create_app(db=db, minter=SlowMinter(), pool=None)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r1, r2 = await asyncio.gather(c.post("/signup", data={"email": "a@x.io"}),
                                      c.post("/signup", data={"email": "a@x.io"}))
    assert r1.status_code == r2.status_code == 303 and SlowMinter.calls == 1
