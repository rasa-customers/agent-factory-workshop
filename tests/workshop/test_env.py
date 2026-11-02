from workshop.env import Settings, check_settings


def make(**kw):
    base = dict(openai_api_key="sk-x", openai_base_url="https://p/v1", rasa_license="lic")
    base.update(kw)
    return Settings(_env_file=None, **base)


def test_check_settings_flags_missing_license():
    assert any("RASA_LICENSE" in p for p in check_settings(make(rasa_license=None)))


def test_check_settings_ok():
    assert check_settings(make()) == []


def test_base_url_must_end_with_v1():
    assert any("/v1" in p for p in check_settings(make(openai_base_url="https://p")))


def test_missing_llm_key_flagged():
    assert any("OPENAI_API_KEY" in p for p in check_settings(make(openai_api_key="")))


def test_export_settings_fills_defaults_but_keeps_existing(monkeypatch):
    from workshop.env import export_settings
    monkeypatch.delenv("FACTORY_MODEL", raising=False)
    monkeypatch.setenv("OPENAI_BASE_URL", "https://already-set/v1")
    export_settings(make(openai_base_url="https://p/v1"))
    import os
    assert os.environ["FACTORY_MODEL"] == "gpt-5.2"
    assert os.environ["OPENAI_BASE_URL"] == "https://already-set/v1"


def test_factory_main_exports_settings_before_serving(monkeypatch):
    import factory.server as srv
    called = []
    monkeypatch.setattr(srv, "export_settings", lambda *a, **k: called.append(True), raising=False)
    monkeypatch.setattr("uvicorn.run", lambda *a, **k: called.append("served"))
    srv.main()
    assert called == [True, "served"]
