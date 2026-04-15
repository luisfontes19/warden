from warden.engine.models import Rule

from tests.rule_spec.conftest import tmp_text, tmp_json, tmp_binary


class TestContains:
    def test_text_substring_match(self):
        path = tmp_text("hello world")
        rule = Rule(rule_id="c1", files=[path], patterns=[{"contains": "world"}])
        matches = rule.evaluate()
        assert len(matches) == 1
        assert matches[0].matched_content == "world"

    def test_text_no_match(self):
        path = tmp_text("hello world")
        rule = Rule(rule_id="c2", files=[path], patterns=[{"contains": "missing"}])
        assert rule.evaluate() == []

    def test_binary_content(self):
        path = tmp_binary(b"\x00\x01hello\x02")
        rule = Rule(rule_id="c3", files=[path], filetype="binary", patterns=[{"contains": "hello"}])
        assert len(rule.evaluate()) == 1

    def test_json_array_membership(self):
        path = tmp_json(["a", "b", "c"])
        rule = Rule(rule_id="c4", files=[path], patterns=[{"contains": "b"}])
        matches = rule.evaluate()
        assert len(matches) == 1
        assert matches[0].matched_content == "b"

    def test_json_dict_key_membership(self):
        path = tmp_json({"key1": 1, "key2": 2})
        rule = Rule(rule_id="c5", files=[path], patterns=[{"contains": "key1"}])
        assert len(rule.evaluate()) == 1

    def test_full_string_also_matches(self):
        path = tmp_text("exact")
        rule = Rule(rule_id="c6", files=[path], patterns=[{"contains": "exact"}])
        assert len(rule.evaluate()) == 1


class TestNotContains:
    def test_absent_substring_matches(self):
        path = tmp_text("hello world")
        rule = Rule(rule_id="nc1", files=[path], patterns=[{"not-contains": "missing"}])
        assert len(rule.evaluate()) == 1

    def test_present_substring_no_match(self):
        path = tmp_text("hello world")
        rule = Rule(rule_id="nc2", files=[path], patterns=[{"not-contains": "hello"}])
        assert rule.evaluate() == []

    def test_json_array_not_contains(self):
        path = tmp_json(["a", "b"])
        rule = Rule(rule_id="nc3", files=[path], patterns=[{"not-contains": "z"}])
        matches = rule.evaluate()
        # The extracted content is the array itself (a list), so each item becomes a match
        assert len(matches) == 2
