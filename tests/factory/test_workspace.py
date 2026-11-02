import pytest

from factory.jobs import Job
from factory.workspace import WorkspaceTools, prepare_workspace


@pytest.fixture
def ws(tmp_path):
    (tmp_path / "a.txt").write_text("hi")
    return WorkspaceTools(tmp_path)


def test_write_then_read_roundtrip(ws):
    ws.write_file("static/index.html", "<h1>x</h1>")
    assert ws.read_file("static/index.html") == "<h1>x</h1>"


def test_write_file_rejects_path_escape(ws, tmp_path):
    with pytest.raises(PermissionError):
        ws.write_file("../escape.txt", "no")
    assert not (tmp_path.parent / "escape.txt").exists()


def test_read_absolute_path_outside_rejected(ws):
    with pytest.raises(PermissionError):
        ws.read_file("/etc/hosts")


def test_list_files(ws):
    assert "a.txt" in ws.list_files(".")


async def test_run_command_rejects_non_allowlisted(ws):
    out = await ws.run_command("curl http://example.com")
    assert "not allowed" in out


async def test_run_command_runs_in_root(ws):
    out = await ws.run_command("ls")
    assert "a.txt" in out


async def test_run_command_truncates_output(ws):
    ws.write_file("big.txt", "x" * 20000)
    out = await ws.run_command("cat big.txt")
    assert len(out) <= 8192 + 200 and "truncated" in out


def test_prepare_workspace_dashboard(tmp_path):
    job = Job(id="j1", kind="dashboard", spec="s")
    root = prepare_workspace(job, base=tmp_path)
    assert (root / "app.py").exists() and (root / "static" / "index.html").exists()


def test_prepare_workspace_mantle_sets_travel_mcp(tmp_path):
    job = Job(id="j2", kind="mantle_agent", spec="s")
    root = prepare_workspace(job, base=tmp_path)
    text = (root / "integrations.yml").read_text()
    assert "name: travel" in text and "${OPENAI_BASE_URL}" in text
    assert (root / "skills" / "placeholder" / "skill.md").exists()
