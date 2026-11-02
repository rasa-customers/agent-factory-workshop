import pytest

from infra.aws.common import DOMAIN, assert_safe_record, in_domain


def test_records_inside_the_workshop_domain_are_allowed():
    for name in (f"*.{DOMAIN}", f"_abc.{DOMAIN}.", DOMAIN):
        assert in_domain(name)
        assert_safe_record(name)


@pytest.mark.parametrize("name", [f"x{DOMAIN}", "agent-factory.playground-cse.rasa-dev.io",
                                  "*.agent-factory.playground-cse.rasa-dev.io", "playground-cse.rasa-dev.io"])
def test_anything_else_is_refused(name):
    assert not in_domain(name)
    with pytest.raises(SystemExit):
        assert_safe_record(name)
