from factory.hosting import agent_command


def test_agent_command_serves_rest_and_inspector():
    # `rasa inspect` serves only the Inspector; the checker's talk_to_assistant needs
    # /webhooks/rest/webhook, which `rasa run --inspect` serves alongside the Inspector.
    cmd = agent_command("/x/rasa", 5006)
    assert cmd == ["/x/rasa", "run", "--inspect", "-p", "5006"]
    assert "--enable-api" not in cmd  # VMs are publicly routed; don't expose the model API
