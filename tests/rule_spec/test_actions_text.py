
from warden.engine.actions import ActionResult
from warden.engine.models import Rule

from tests.rule_spec.conftest import tmp_text


class TestActionDelete:
    def test_delete_matched_content(self):
        path = tmp_text("keep BAD keep")
        rule = Rule(
            rule_id="ad1", files=[path],
            patterns=[{"contains": "BAD"}],
            actions=[{"delete": None}],
        )
        matches = rule.evaluate()
        assert rule.apply_actions(matches) == "keep  keep"

    def test_delete_multiple_occurrences(self):
        path = tmp_text("a BAD b BAD c")
        rule = Rule(
            rule_id="ad2", files=[path],
            patterns=[{"match": "BAD"}],
            actions=[{"delete": None}],
        )
        matches = rule.evaluate()
        assert rule.apply_actions(matches) == "a  b  c"


class TestActionReplace:
    def test_replace_matched_content(self):
        path = tmp_text("hello bad world")
        rule = Rule(
            rule_id="ar1", files=[path],
            patterns=[{"contains": "bad"}],
            actions=[{"replace": "good"}],
        )
        matches = rule.evaluate()
        assert rule.apply_actions(matches) == "hello good world"

    def test_replace_with_empty_string(self):
        path = tmp_text("hello bad world")
        rule = Rule(
            rule_id="ar2", files=[path],
            patterns=[{"contains": "bad "}],
            actions=[{"replace": ""}],
        )
        matches = rule.evaluate()
        assert rule.apply_actions(matches) == "hello world"


class TestActionAdd:
    def test_add_appends(self):
        path = tmp_text("line1")
        rule = Rule(
            rule_id="aa1", files=[path],
            patterns=[{"contains": "line1"}],
            actions=[{"add": "\nline2"}],
        )
        matches = rule.evaluate()
        assert rule.apply_actions(matches) == "line1\nline2"


class TestActionDeleteFile:
    def test_returns_file_deleted(self):
        path = tmp_text("content")
        rule = Rule(
            rule_id="df1", files=[path],
            patterns=[{"contains": "content"}],
            actions=[{"delete-file": None}],
        )
        matches = rule.evaluate()
        assert rule.apply_actions(matches) is ActionResult.FILE_DELETED
