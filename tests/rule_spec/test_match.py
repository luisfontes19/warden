from tests.rule_spec.conftest import tmp_text
from warden.engine.models import Rule
from warden.engine.patterns import RegexMatchResult


class TestMatch:
    def test_numeric_pattern(self):
        path = tmp_text("error code 404 found")
        rule = Rule(rule_id="m1", files=[path], patterns=[{"match": r"\d{3}"}])
        matches = rule.evaluate()
        assert len(matches) == 1
        assert matches[0].matched_content == "404"

    def test_no_match(self):
        path = tmp_text("no numbers here")
        rule = Rule(rule_id="m2", files=[path], patterns=[{"match": r"\d+"}])
        assert rule.evaluate() == []

    def test_version_string(self):
        path = tmp_text("version=1.2.3")
        rule = Rule(rule_id="m3", files=[path], patterns=[{"match": r"version=\d+\.\d+\.\d+"}])
        matches = rule.evaluate()
        assert matches[0].matched_content == "version=1.2.3"

    def test_multiline_content(self):
        path = tmp_text("line1\nSECRET=abc123\nline3")
        rule = Rule(rule_id="m4", files=[path], patterns=[{"match": r"SECRET=\w+"}])
        matches = rule.evaluate()
        assert matches[0].matched_content == "SECRET=abc123"

    def test_case_sensitive(self):
        path = tmp_text("Hello World")
        rule = Rule(rule_id="m5", files=[path], patterns=[{"match": r"hello"}])
        assert rule.evaluate() == []

    def test_case_insensitive_flag(self):
        path = tmp_text("Hello World")
        rule = Rule(rule_id="m6", files=[path], patterns=[{"match": r"(?i)hello"}])
        assert len(rule.evaluate()) == 1

    def test_named_groups_in_matched_content(self):
        path = tmp_text("version=1.2.3")
        rule = Rule(rule_id="m7", files=[path], patterns=[{"match": r"(?P<key>version)=(?P<value>[\d.]+)"}])
        matches = rule.evaluate()
        assert len(matches) == 1
        result = matches[0].matched_content
        assert isinstance(result, RegexMatchResult)
        assert str(result) == "version=1.2.3"
        assert result.groups == {"key": "version", "value": "1.2.3"}
        assert result.group == ["version", "1.2.3"]

    def test_named_groups_replace_action(self):
        path = tmp_text("version=1.2.3\nother=foo\n")
        rule = Rule(
            rule_id="m8",
            files=[path],
            patterns=[{"match": r"(?P<key>version)=(?P<value>[\d.]+)"}],
            actions=[{"replace": "${{ groups.key }}=REDACTED"}],
        )
        rule.evaluate()
        result = rule.apply_actions(rule.evaluate())
        assert "version=REDACTED" in result
        assert "1.2.3" not in result

    def test_positional_groups_replace_action(self):
        path = tmp_text("version=9.9.9\nenv=staging\n")
        rule = Rule(
            rule_id="m9",
            files=[path],
            patterns=[{"match": r"(version)=([\d.]+)"}],
            actions=[{"replace": "${{ group[0] }}=REDACTED"}],
        )
        result = rule.apply_actions(rule.evaluate())
        assert "version=REDACTED" in result
        assert "9.9.9" not in result
