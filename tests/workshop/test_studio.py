"""Conversations go to Rasa Studio only where Studio is set up (cloud machines), never on laptops."""
from pathlib import Path

from workshop.studio import add_event_broker, event_broker_yaml, write_integrations

BASE = "model_groups: []\n"


def test_no_studio_no_event_broker():
    assert event_broker_yaml({}) == ""


def test_studio_event_broker_is_plain_kafka_on_the_studio_topic():
    text = event_broker_yaml({"STUDIO_KAFKA_URL": "10.77.1.5:29092"})
    assert "event_broker:" in text and "type: kafka" in text and "url: 10.77.1.5:29092" in text
    assert "topic: rasa-events" in text and "security_protocol: PLAINTEXT" in text


def test_write_integrations_copies_the_base_without_studio(tmp_path):
    (tmp_path / "integrations.base.yml").write_text(BASE)
    write_integrations(tmp_path, env={})
    assert (tmp_path / "integrations.yml").read_text() == BASE


def test_write_integrations_adds_studio_when_configured(tmp_path):
    (tmp_path / "integrations.base.yml").write_text(BASE)
    write_integrations(tmp_path, env={"STUDIO_KAFKA_URL": "10.77.1.5:29092"})
    text = (tmp_path / "integrations.yml").read_text()
    assert text.startswith(BASE) and text.count("event_broker:") == 1


def test_add_event_broker_to_a_built_agent_once(tmp_path):
    (tmp_path / "integrations.yml").write_text(BASE)
    env = {"STUDIO_KAFKA_URL": "10.77.1.5:29092"}
    add_event_broker(tmp_path, env)
    add_event_broker(tmp_path, env)
    assert (tmp_path / "integrations.yml").read_text().count("event_broker:") == 1


def test_the_foreman_keeps_its_base_config_in_git():
    repo = Path(__file__).parents[2]
    assert (repo / "foreman" / "integrations.base.yml").exists()
    assert "foreman/integrations.yml" in (repo / ".gitignore").read_text()


def test_built_agents_always_report_as_travel_agent(tmp_path):
    from workshop.studio import AGENT_ID, set_agent_id
    (tmp_path / "agent.yml").write_text("agent:\n  id: whatever-the-builder-chose\n  language: en\n\norchestrator:\n  model_group: main_model\n")
    set_agent_id(tmp_path)
    text = (tmp_path / "agent.yml").read_text()
    assert f"  id: {AGENT_ID}\n" in text and "whatever" not in text and AGENT_ID == "travel-agent"
    assert "language: en" in text and "model_group: main_model" in text
