import json

from warden.rules_engine import Match, Rule
from tests.rule_spec.conftest import tmp_text


class TestMatchObject:
    def test_to_dict(self):
        m = Match(
            rule_id="r1", description="desc", file="/tmp/f.txt",
            matched_content="val", file_content="full",
        )
        d = m.to_dict()
        assert d["rule_id"] == "r1"
        assert d["file"] == "/tmp/f.txt"
        assert d["matched_content"] == "val"
        assert d["file_content"] == "full"

    def test_repr_is_json(self):
        m = Match(rule_id="r1", description="", file="f", matched_content=None)
        parsed = json.loads(repr(m))
        assert parsed["rule_id"] == "r1"


class TestApplyActionsEdgeCases:
    def test_no_actions_returns_none(self):
        path = tmp_text("hello")
        rule = Rule(rule_id="e1", files=[path], patterns=[{"contains": "hello"}], actions=[])
        matches = rule.evaluate()
        assert rule.apply_actions(matches) is None

    def test_no_matches_returns_none(self):
        rule = Rule(rule_id="e2", files=["dummy"], actions=[{"delete": None}])
        assert rule.apply_actions([]) is None
