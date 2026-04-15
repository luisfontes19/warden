import json

from warden.rules_engine import Rule
from tests.rule_spec.conftest import tmp_json


class TestJsonReplaceNull:
    def test_null_uses_matched_content(self):
        path = tmp_json({"servers": {"evil": True, "good": True}})
        rule = Rule(
            rule_id="jr1", files=[path],
            patterns=[{"jq": ".servers.evil"}],
            actions=[{"replace": None}],
        )
        matches = rule.evaluate()
        result = rule.apply_actions(matches)
        assert json.loads(result) is True


class TestJsonReplaceJq:
    def test_jq_delete_key(self):
        data = {"items": [1, 2, 3], "extra": "remove"}
        path = tmp_json(data)
        rule = Rule(
            rule_id="jr2", files=[path],
            patterns=[{"jq": ".extra"}],
            actions=[{"replace": {"jq": "del(.extra)"}}],
        )
        matches = rule.evaluate()
        parsed = json.loads(rule.apply_actions(matches))
        assert "extra" not in parsed
        assert parsed["items"] == [1, 2, 3]

    def test_jq_transform_value(self):
        path = tmp_json({"count": 5})
        rule = Rule(
            rule_id="jr5", files=[path],
            patterns=[{"jq": ".count"}],
            actions=[{"replace": {"jq": ".count + 1 | {count: .}"}}],
        )
        matches = rule.evaluate()
        assert json.loads(rule.apply_actions(matches)) == {"count": 6}


class TestJsonReplaceStr:
    def test_str_literal(self):
        path = tmp_json({"old": True})
        rule = Rule(
            rule_id="jr3", files=[path],
            patterns=[{"jq": ".old"}],
            actions=[{"replace": {"str": '{"new": true}'}}],
        )
        matches = rule.evaluate()
        assert json.loads(rule.apply_actions(matches)) == {"new": True}


class TestJsonReplacePlainString:
    def test_plain_string(self):
        path = tmp_json({"a": 1})
        rule = Rule(
            rule_id="jr4", files=[path],
            patterns=[{"jq": ".a"}],
            actions=[{"replace": '{"b": 2}'}],
        )
        matches = rule.evaluate()
        assert json.loads(rule.apply_actions(matches)) == {"b": 2}
