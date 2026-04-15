from warden.rules_engine import Rule
from tests.rule_spec.conftest import tmp_text


class TestNoPatterns:
    def test_matches_any_existing_file(self):
        path = tmp_text("anything")
        rule = Rule(rule_id="np1", files=[path], patterns=None)
        matches = rule.evaluate()
        assert len(matches) == 1
        assert matches[0].matched_content is None


class TestDescription:
    def test_propagated_to_match(self):
        path = tmp_text("hello")
        rule = Rule(
            rule_id="d1", files=[path], description="Check greeting",
            patterns=[{"contains": "hello"}],
        )
        assert rule.evaluate()[0].description == "Check greeting"

    def test_empty_by_default(self):
        path = tmp_text("hello")
        rule = Rule(rule_id="d2", files=[path], patterns=[{"contains": "hello"}])
        assert rule.evaluate()[0].description == ""
