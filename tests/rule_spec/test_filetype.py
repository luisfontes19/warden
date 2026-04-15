import json

from warden.engine.models import Rule

from tests.rule_spec.conftest import tmp_text


class TestFiletype:
    def test_json_filetype_on_txt_extension(self):
        data = {"key": "value"}
        path = tmp_text(json.dumps(data), suffix=".txt")
        rule = Rule(rule_id="ft1", files=[path], filetype="json", patterns=[{"jq": ".key"}])
        matches = rule.evaluate()
        assert len(matches) == 1
        assert matches[0].matched_content == "value"

    def test_text_filetype_on_json_extension(self):
        path = tmp_text('{"key": "val"}', suffix=".json")
        rule = Rule(rule_id="ft2", files=[path], filetype="text", patterns=[{"contains": '"key"'}])
        assert len(rule.evaluate()) == 1

    def test_binary_filetype(self):
        from tests.rule_spec.conftest import tmp_binary
        path = tmp_binary(b"\x00\x01marker\x02", suffix=".dat")
        rule = Rule(rule_id="ft3", files=[path], filetype="binary", patterns=[{"contains": "marker"}])
        assert len(rule.evaluate()) == 1
