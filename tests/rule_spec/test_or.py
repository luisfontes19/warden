from warden.rules_engine import Rule
from tests.rule_spec.conftest import tmp_text


class TestOr:
    def test_first_matches(self):
        path = tmp_text("alpha")
        rule = Rule(rule_id="or1", files=[path], patterns=[
            {"or": [{"contains": "alpha"}, {"contains": "beta"}]},
        ])
        assert len(rule.evaluate()) == 1

    def test_second_matches(self):
        path = tmp_text("beta")
        rule = Rule(rule_id="or2", files=[path], patterns=[
            {"or": [{"contains": "alpha"}, {"contains": "beta"}]},
        ])
        assert len(rule.evaluate()) == 1

    def test_none_matches(self):
        path = tmp_text("gamma")
        rule = Rule(rule_id="or3", files=[path], patterns=[
            {"or": [{"contains": "alpha"}, {"contains": "beta"}]},
        ])
        assert rule.evaluate() == []

    def test_both_match_returns_multiple(self):
        path = tmp_text("alpha beta")
        rule = Rule(rule_id="or4", files=[path], patterns=[
            {"or": [{"contains": "alpha"}, {"contains": "beta"}]},
        ])
        matches = rule.evaluate()
        assert len(matches) == 2

    def test_three_branches_one_hits(self):
        path = tmp_text("gamma")
        rule = Rule(rule_id="or5", files=[path], patterns=[
            {"or": [
                {"contains": "alpha"},
                {"contains": "beta"},
                {"contains": "gamma"},
            ]},
        ])
        assert len(rule.evaluate()) == 1

    def test_or_with_regex(self):
        path = tmp_text("error 503")
        rule = Rule(rule_id="or6", files=[path], patterns=[
            {"or": [{"match": r"error \d+"}, {"contains": "warning"}]},
        ])
        matches = rule.evaluate()
        assert len(matches) == 1
        assert matches[0].matched_content == "error 503"

    def test_single_branch_or(self):
        path = tmp_text("only option")
        rule = Rule(rule_id="or7", files=[path], patterns=[
            {"or": [{"contains": "only"}]},
        ])
        assert len(rule.evaluate()) == 1
