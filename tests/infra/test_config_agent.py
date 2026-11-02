from infra.portal.caddy import render_caddyfile
from infra.vm.config_agent import public_urls, render_env

DOMAIN = "fw.example"


def test_render_env_includes_license_when_present():
    text = render_env({"OPENAI_API_KEY": "sk-1", "OPENAI_BASE_URL": "https://llm/v1", "RASA_LICENSE": "LIC"}, "vm-03", DOMAIN)
    assert "RASA_LICENSE=LIC" in text and "OPENAI_API_KEY=sk-1" in text


def test_render_env_omits_license_when_absent():
    text = render_env({"OPENAI_API_KEY": "sk-1", "OPENAI_BASE_URL": "https://llm/v1"}, "vm-03", DOMAIN)
    assert "RASA_LICENSE" not in text


def test_render_env_sets_public_urls():
    text = render_env({"OPENAI_API_KEY": "k", "OPENAI_BASE_URL": "u"}, "vm-03", DOMAIN)
    assert "FACTORY_PUBLIC_URL=https://vm-03-factory.fw.example" in text
    assert "DASHBOARD_PUBLIC_URL=https://vm-03-dashboard.fw.example" in text
    assert "AGENT_PUBLIC_URL=https://vm-03-agent.fw.example" in text
    assert "FOREMAN_PUBLIC_URL=https://vm-03-foreman.fw.example" in text


def test_public_urls_code_is_bare_vm_host():
    assert public_urls("vm-03", DOMAIN)["code"] == "https://vm-03.fw.example"


def test_render_caddyfile_routes():
    vms = [{"id": "vm-01", "ip": "10.0.0.5", "state": "ready"}, {"id": "vm-02", "ip": None, "state": "launching"}]
    text = render_caddyfile(vms, DOMAIN)
    assert "vm-01.fw.example" in text and "10.0.0.5:8080" in text
    assert "vm-01-foreman.fw.example" in text and "10.0.0.5:5005" in text
    assert "vm-01-agent.fw.example" in text and "10.0.0.5:5006" in text
    assert "vm-01-dashboard.fw.example" in text and "10.0.0.5:8600" in text
    assert "vm-01-factory.fw.example" in text and "10.0.0.5:8800" in text
    assert "vm-02" not in text
    assert "portal.fw.example" in text and "llm.fw.example" in text
    # TLS ends at the load balancer (ACM wildcard); Caddy serves plain HTTP and routes by Host
    assert "http://portal.fw.example" in text and "http://vm-01-foreman.fw.example" in text
    assert "tls " not in text


def test_apply_resets_failed_service_and_keeps_editor_when_password_unchanged(tmp_path, monkeypatch):
    import infra.vm.config_agent as ca
    calls = []
    monkeypatch.setattr(ca, "REPO", tmp_path)
    monkeypatch.setattr(ca, "CODE_SERVER_CONFIG", tmp_path / "cs" / "config.yaml")
    monkeypatch.setattr(ca.subprocess, "run", lambda cmd, **kw: calls.append(cmd))
    cfg = {"password": "pw", "env": {"OPENAI_API_KEY": "sk-1", "OPENAI_BASE_URL": "https://llm/v1"}}
    ca.apply(cfg, "vm-03", DOMAIN)
    assert ["systemctl", "restart", "code-server@workshop"] in calls
    # a license pasted later: workshop-up may have hit its start limit, so reset it; the editor stays up
    calls.clear()
    ca.apply({**cfg, "env": {**cfg["env"], "RASA_LICENSE": "LIC"}}, "vm-03", DOMAIN)
    assert ["systemctl", "restart", "code-server@workshop"] not in calls
    assert calls.index(["systemctl", "reset-failed", "workshop-up"]) < calls.index(["systemctl", "restart", "workshop-up"])
