from warden.engine.models import Rule

from tests.rule_spec.conftest import tmp_text, tmp_json


class TestNestedOrInsideAnd:
    def test_or_as_second_and_branch(self):
        path = tmp_text("critical error in module")
        rule = Rule(rule_id="n1", files=[path], patterns=[
            {"and": [
                {"contains": "error"},
                {"or": [{"contains": "critical"}, {"contains": "fatal"}]},
            ]},
        ])
        assert len(rule.evaluate()) >= 1

    def test_or_as_first_and_branch(self):
        path = tmp_text("fatal warning detected")
        rule = Rule(rule_id="n2", files=[path], patterns=[
            {"and": [
                {"or": [{"contains": "fatal"}, {"contains": "critical"}]},
                {"contains": "detected"},
            ]},
        ])
        assert len(rule.evaluate()) >= 1

    def test_or_inside_and_none_in_or(self):
        path = tmp_text("info message only")
        rule = Rule(rule_id="n3", files=[path], patterns=[
            {"and": [
                {"contains": "info"},
                {"or": [{"contains": "error"}, {"contains": "fatal"}]},
            ]},
        ])
        assert rule.evaluate() == []

    def test_or_inside_and_and_branch_fails(self):
        path = tmp_text("critical but no keyword")
        rule = Rule(rule_id="n4", files=[path], patterns=[
            {"and": [
                {"or": [{"contains": "critical"}, {"contains": "fatal"}]},
                {"contains": "error"},
            ]},
        ])
        assert rule.evaluate() == []


class TestNestedAndInsideOr:
    def test_first_and_branch_matches(self):
        path = tmp_text("warning: disk full")
        rule = Rule(rule_id="n5", files=[path], patterns=[
            {"or": [
                {"and": [{"contains": "warning"}, {"contains": "disk"}]},
                {"contains": "critical"},
            ]},
        ])
        assert len(rule.evaluate()) >= 1

    def test_second_or_branch_matches(self):
        path = tmp_text("critical failure")
        rule = Rule(rule_id="n6", files=[path], patterns=[
            {"or": [
                {"and": [{"contains": "warning"}, {"contains": "disk"}]},
                {"contains": "critical"},
            ]},
        ])
        assert len(rule.evaluate()) >= 1

    def test_neither_branch_matches(self):
        path = tmp_text("all clear")
        rule = Rule(rule_id="n7", files=[path], patterns=[
            {"or": [
                {"and": [{"contains": "warning"}, {"contains": "disk"}]},
                {"contains": "critical"},
            ]},
        ])
        assert rule.evaluate() == []


class TestDeeplyNested:
    def test_or_inside_and_inside_or(self):
        """or > and > or three levels deep."""
        path = tmp_text("error 500 critical system")
        rule = Rule(rule_id="deep1", files=[path], patterns=[
            {"or": [
                {"and": [
                    {"or": [{"contains": "500"}, {"contains": "503"}]},
                    {"contains": "critical"},
                ]},
                {"contains": "panic"},
            ]},
        ])
        assert len(rule.evaluate()) >= 1

    def test_and_inside_or_inside_and(self):
        """and > or > and three levels deep."""
        path = tmp_text("server error disk full")
        rule = Rule(rule_id="deep2", files=[path], patterns=[
            {"and": [
                {"or": [
                    {"and": [{"contains": "server"}, {"contains": "error"}]},
                    {"and": [{"contains": "client"}, {"contains": "timeout"}]},
                ]},
                {"contains": "disk"},
            ]},
        ])
        assert len(rule.evaluate()) >= 1

    def test_deep_nesting_fails_at_leaf(self):
        """All structure matches except the deepest leaf."""
        path = tmp_text("server ok disk full")
        rule = Rule(rule_id="deep3", files=[path], patterns=[
            {"and": [
                {"or": [
                    {"and": [{"contains": "server"}, {"contains": "error"}]},
                    {"and": [{"contains": "client"}, {"contains": "timeout"}]},
                ]},
                {"contains": "disk"},
            ]},
        ])
        assert rule.evaluate() == []

    def test_or_of_ors(self):
        path = tmp_text("gamma")
        rule = Rule(rule_id="deep4", files=[path], patterns=[
            {"or": [
                {"or": [{"contains": "alpha"}, {"contains": "beta"}]},
                {"or": [{"contains": "gamma"}, {"contains": "delta"}]},
            ]},
        ])
        assert len(rule.evaluate()) >= 1

    def test_and_of_ands(self):
        path = tmp_text("a b c d")
        rule = Rule(rule_id="deep5", files=[path], patterns=[
            {"and": [
                {"and": [{"contains": "a"}, {"contains": "b"}]},
                {"and": [{"contains": "c"}, {"contains": "d"}]},
            ]},
        ])
        assert len(rule.evaluate()) >= 1

    def test_and_of_ands_partial_fail(self):
        path = tmp_text("a b c")
        rule = Rule(rule_id="deep6", files=[path], patterns=[
            {"and": [
                {"and": [{"contains": "a"}, {"contains": "b"}]},
                {"and": [{"contains": "c"}, {"contains": "d"}]},
            ]},
        ])
        assert rule.evaluate() == []


class TestNestedWithMixedMatchers:
    def test_regex_inside_or(self):
        path = tmp_text("code 404 not found")
        rule = Rule(rule_id="mix1", files=[path], patterns=[
            {"or": [{"match": r"\b5\d{2}\b"}, {"match": r"\b4\d{2}\b"}]},
        ])
        matches = rule.evaluate()
        assert len(matches) == 1
        assert matches[0].matched_content == "404"

    def test_not_contains_inside_and(self):
        path = tmp_text("production server running")
        rule = Rule(rule_id="mix2", files=[path], patterns=[
            {"and": [
                {"contains": "production"},
                {"not-contains": "debug"},
            ]},
        ])
        assert len(rule.evaluate()) >= 1

    def test_not_contains_inside_and_fails(self):
        path = tmp_text("production debug server")
        rule = Rule(rule_id="mix3", files=[path], patterns=[
            {"and": [
                {"contains": "production"},
                {"not-contains": "debug"},
            ]},
        ])
        assert rule.evaluate() == []

    def test_jq_inside_or(self):
        path = tmp_json({"level": "warn", "code": 42})
        rule = Rule(rule_id="mix4", files=[path], patterns=[
            {"or": [
                {"jq": '.level == "error"'},
                {"jq": ".code == 42"},
            ]},
        ])
        assert len(rule.evaluate()) >= 1

    def test_equals_inside_and_with_implicit_and(self):
        """Implicit AND list containing an explicit and node."""
        path = tmp_text("exact match")
        rule = Rule(rule_id="mix5", files=[path], patterns=[
            {"not-equals": "something else"},
            {"and": [{"contains": "exact"}, {"contains": "match"}]},
        ])
        assert len(rule.evaluate()) >= 1
