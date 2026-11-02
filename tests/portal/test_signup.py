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
