from warden.engine.models import Rule

from tests.rule_spec.conftest import tmp_json


class TestJq:
    def test_select_field(self):
        path = tmp_json({"name": "warden", "version": 2})
        rule = Rule(rule_id="jq1", files=[path], patterns=[{"jq": ".name"}])
        matches = rule.evaluate()
        assert len(matches) == 1
        assert matches[0].matched_content == "warden"

    def test_length_comparison(self):
        path = tmp_json({"items": [1, 2, 3]})
        rule = Rule(rule_id="jq2", files=[path], patterns=[{"jq": ".items | length > 2"}])
        assert len(rule.evaluate()) == 1

    def test_falsy_value_no_match(self):
        path = tmp_json({"enabled": False})
        rule = Rule(rule_id="jq3", files=[path], patterns=[{"jq": ".enabled"}])
        assert rule.evaluate() == []

    def test_nested_key(self):
        path = tmp_json({"server": {"host": "localhost", "port": 8080}})
        rule = Rule(rule_id="jq4", files=[path], patterns=[{"jq": ".server.port"}])
        matches = rule.evaluate()
        assert matches[0].matched_content == 8080

    def test_null_field_no_match(self):
        path = tmp_json({"key": None})
        rule = Rule(rule_id="jq5", files=[path], patterns=[{"jq": ".key"}])
        assert rule.evaluate() == []

    def test_missing_field_no_match(self):
        path = tmp_json({"a": 1})
        rule = Rule(rule_id="jq6", files=[path], patterns=[{"jq": ".nonexistent"}])
        assert rule.evaluate() == []

    def test_array_select_returns_list(self):
        data = {"servers": {"a": {"bad": True}, "b": {"bad": True}, "c": {"bad": False}}}
        path = tmp_json(data)
        rule = Rule(rule_id="jq7", files=[path], patterns=[
            {"jq": '.servers | to_entries[] | select(.value.bad) | .key'},
        ])
        matches = rule.evaluate()
        assert len(matches) == 2
        assert {m.matched_content for m in matches} == {"a", "b"}

    def test_has_key_check(self):
        path = tmp_json({"mcpServers": {"evil": {}}})
        rule = Rule(rule_id="jq8", files=[path], patterns=[{"jq": '.mcpServers | has("evil")'}])
        assert len(rule.evaluate()) == 1
