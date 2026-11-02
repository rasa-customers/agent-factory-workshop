from factory.agents import CheckReport, make_builder, make_checker
from factory.workspace import WorkspaceTools


def test_builder_dashboard_has_write_tools_and_contract(tmp_path):
    a = make_builder("dashboard", WorkspaceTools(tmp_path), mcp_servers=[])
    names = {t.name for t in a.tools}
    assert {"write_file", "run_command"} <= names
    assert "static/" in a.instructions and "app.py" in a.instructions


def test_checker_cannot_write_and_returns_report(tmp_path):
    a = make_checker("dashboard", tools=[])
    assert a.output_type is CheckReport
    assert "spec" in a.instructions.lower() and "never read" in a.instructions.lower()


def test_builder_mantle_mentions_travel_tools(tmp_path):
    a = make_builder("mantle_agent", WorkspaceTools(tmp_path), mcp_servers=[])
    assert "mcp/travel" in a.instructions and "BUILDING.md" in a.instructions
