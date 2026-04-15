from warden.rules_engine import Rule
from tests.rule_spec.conftest import tmp_text, tmp_json


class TestEquals:
    def test_text_exact_match(self):
        path = tmp_text("exact")
        rule = Rule(rule_id="eq1", files=[path], patterns=[{"equals": "exact"}])
        assert len(rule.evaluate()) == 1

    def test_text_no_match(self):
        path = tmp_text("exact plus more")
        rule = Rule(rule_id="eq2", files=[path], patterns=[{"equals": "exact"}])
        assert rule.evaluate() == []

    def test_json_object(self):
        path = tmp_json({"a": 1})
        rule = Rule(rule_id="eq3", files=[path], patterns=[{"equals": {"a": 1}}])
        assert len(rule.evaluate()) == 1

    def test_json_array(self):
        path = tmp_json([1, 2, 3])
        rule = Rule(rule_id="eq4", files=[path], patterns=[{"equals": [1, 2, 3]}])
        matches = rule.evaluate()
        # Extracted content is a list, so each item becomes a separate match
        assert len(matches) == 3

    def test_json_object_mismatch(self):
        path = tmp_json({"a": 1})
        rule = Rule(rule_id="eq5", files=[path], patterns=[{"equals": {"a": 2}}])
        assert rule.evaluate() == []


class TestNotEquals:
    def test_different_content_matches(self):
        path = tmp_text("something")
        rule = Rule(rule_id="ne1", files=[path], patterns=[{"not-equals": "other"}])
        assert len(rule.evaluate()) == 1

    def test_same_content_no_match(self):
        path = tmp_text("exact")
        rule = Rule(rule_id="ne2", files=[path], patterns=[{"not-equals": "exact"}])
        assert rule.evaluate() == []

    def test_json_not_equals(self):
        path = tmp_json({"a": 1})
        rule = Rule(rule_id="ne3", files=[path], patterns=[{"not-equals": {"a": 2}}])
        assert len(rule.evaluate()) == 1
