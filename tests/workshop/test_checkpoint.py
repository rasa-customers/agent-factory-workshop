import pytest

from workshop.procs import CHECKPOINTS, install_checkpoint


@pytest.fixture
def repo(tmp_path):
    src = tmp_path / "repo" / "checkpoints" / "02-dashboard-built" / "dashboard"
    (src / "static").mkdir(parents=True)
    (src / "app.py").write_text("app")
    (src / "static" / "index.html").write_text("<h1>built</h1>")
    return tmp_path / "repo"


def test_checkpoint_copies_into_latest(repo, tmp_path):
    kind, dest = install_checkpoint("02-dashboard-built", repo=repo, workspace=tmp_path / "ws")
    assert kind == "dashboard"
    assert (dest / "static" / "index.html").read_text() == "<h1>built</h1>"
    assert dest == tmp_path / "ws" / "latest-dashboard"


def test_checkpoint_replaces_previous_latest(repo, tmp_path):
    old = tmp_path / "ws" / "latest-dashboard"
    old.mkdir(parents=True)
    (old / "stale.txt").write_text("x")
    _, dest = install_checkpoint("02-dashboard-built", repo=repo, workspace=tmp_path / "ws")
    assert not (dest / "stale.txt").exists()


def test_unknown_checkpoint_lists_valid_names(repo, tmp_path):
    with pytest.raises(SystemExit) as e:
        install_checkpoint("99-nope", repo=repo, workspace=tmp_path / "ws")
    assert all(n in str(e.value) for n in CHECKPOINTS)


def test_watch_reports_failure_when_a_service_dies():
    # systemd only restarts the cloud machine's stack (Restart=on-failure) if `workshop up` exits non-zero
    import subprocess, sys
    from workshop.procs import watch
    dead = subprocess.Popen([sys.executable, "-c", "pass"]); dead.wait()
    assert watch([dead]) == 1


def test_extended_checkpoints_exist_in_the_repo():
    from workshop.procs import CHECKPOINTS, REPO
    for name in ("02b-dashboard-extended", "03b-agent-extended"):
        kind, sub, _ = CHECKPOINTS[name]
        root = REPO / "checkpoints" / name / sub
        assert (root / ("static/index.html" if kind == "dashboard" else "agent.yml")).exists()
    skills = {p.name for p in (REPO / "checkpoints" / "03b-agent-extended" / "travel-agent" / "skills").iterdir()}
    assert len(skills) >= 3 and "placeholder" not in skills
