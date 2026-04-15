from warden.engine.models import Rule

from tests.rule_spec.conftest import tmp_text


class TestAnd:
    def test_all_match(self):
        path = tmp_text("alpha beta gamma")
        rule = Rule(rule_id="and1", files=[path], patterns=[
            {"and": [{"contains": "alpha"}, {"contains": "beta"}]},
        ])
        assert len(rule.evaluate()) >= 1

    def test_partial_no_match(self):
        path = tmp_text("alpha only")
        rule = Rule(rule_id="and2", files=[path], patterns=[
            {"and": [{"contains": "alpha"}, {"contains": "beta"}]},
        ])
        assert rule.evaluate() == []

    def test_extracted_values(self):
        path = tmp_text("hello world")
        rule = Rule(rule_id="and3", files=[path], patterns=[
            {"and": [{"contains": "hello"}, {"contains": "world"}]},
        ])
        matches = rule.evaluate()
        assert len(matches) == 2
        extracted = {m.matched_content for m in matches}
        assert extracted == {"hello", "world"}

    def test_three_conditions(self):
        path = tmp_text("a b c")
        rule = Rule(rule_id="and4", files=[path], patterns=[
            {"and": [{"contains": "a"}, {"contains": "b"}, {"contains": "c"}]},
        ])
        assert len(rule.evaluate()) >= 1

    def test_and_with_regex_and_contains(self):
        path = tmp_text("error code 500 critical")
        rule = Rule(rule_id="and5", files=[path], patterns=[
            {"and": [{"match": r"\d{3}"}, {"contains": "critical"}]},
        ])
        matches = rule.evaluate()
        assert len(matches) == 2
        contents = {m.matched_content for m in matches}
        assert "500" in contents
        assert "critical" in contents

    def test_single_condition_and(self):
        path = tmp_text("hello")
        rule = Rule(rule_id="and6", files=[path], patterns=[
            {"and": [{"contains": "hello"}]},
        ])
        assert len(rule.evaluate()) == 1


class TestImplicitAnd:
    """A list of patterns at the top level is an implicit AND."""

    def test_all_patterns_must_match(self):
        path = tmp_text("foo bar baz")
        rule = Rule(rule_id="ia1", files=[path], patterns=[
            {"contains": "foo"},
            {"contains": "bar"},
        ])
        assert len(rule.evaluate()) >= 1

    def test_one_fails_means_no_match(self):
        path = tmp_text("foo only")
        rule = Rule(rule_id="ia2", files=[path], patterns=[
            {"contains": "foo"},
            {"contains": "bar"},
        ])
        assert rule.evaluate() == []

    def test_single_pattern_in_list(self):
        path = tmp_text("hello")
        rule = Rule(rule_id="ia3", files=[path], patterns=[{"contains": "hello"}])
        assert len(rule.evaluate()) == 1

    def test_dict_pattern_not_wrapped_in_list(self):
        """A single dict pattern (not in a list) also works."""
        path = tmp_text("hello")
        rule = Rule(rule_id="ia4", files=[path], patterns={"contains": "hello"})
        assert len(rule.evaluate()) == 1
