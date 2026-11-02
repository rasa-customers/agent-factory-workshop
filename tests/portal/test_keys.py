import httpx
import pytest
import respx

from infra.portal.keys import revoke_all_keys

BASE = "https://llm.example"


@respx.mock
def test_revoke_all_pages_through_and_deletes_every_key():
    pages = {1: ["h1", "h2"], 2: ["h3"]}
    respx.get(f"{BASE}/key/list").mock(side_effect=lambda req: httpx.Response(200, json={
        "keys": pages[int(req.url.params["page"])], "total_pages": 2}))
    deleted = respx.post(f"{BASE}/key/delete").mock(return_value=httpx.Response(200, json={}))
    assert revoke_all_keys(BASE, "sk-master") == 3
    sent = [k for call in deleted.calls for k in __import__("json").loads(call.request.content)["keys"]]
    assert sorted(sent) == ["h1", "h2", "h3"]
    assert all(int(c.request.url.params["size"]) <= 100 for c in respx.calls if c.request.url.path == "/key/list")


@respx.mock
def test_revoke_all_fails_loudly_instead_of_reporting_zero():
    respx.get(f"{BASE}/key/list").mock(return_value=httpx.Response(422, json={"detail": "size too large"}))
    with pytest.raises(httpx.HTTPStatusError):
        revoke_all_keys(BASE, "sk-master")
