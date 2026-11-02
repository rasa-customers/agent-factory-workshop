from types import SimpleNamespace

from factory.checks.mantle import train_project


def test_train_project_reports_success(tmp_path):
    ok = train_project(tmp_path, run=lambda *a, **k: SimpleNamespace(returncode=0, stdout="saved", stderr=""))
    assert ok.startswith("OK")


def test_train_project_returns_real_errors(tmp_path):
    out = '{"event_info": "Skill directory \'skills/x\' failed to load: Unknown key(s): id", "level": "error"}'
    msg = train_project(tmp_path, run=lambda *a, **k: SimpleNamespace(returncode=1, stdout=out, stderr=""))
    assert msg.startswith("FAILED") and "Unknown key(s): id" in msg
