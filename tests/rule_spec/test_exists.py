from warden.rules_engine import Rule
from tests.rule_spec.conftest import tmp_text


class TestExists:
    def test_existing_file_matches(self):
        path = tmp_text("hello")
        rule = Rule(rule_id="ex1", files=[path], patterns=[{"exists": None}])
        assert len(rule.evaluate()) == 1

    def test_missing_file_no_match(self):
        rule = Rule(
            rule_id="ex2",
            files=["/tmp/_warden_nonexistent_12345.txt"],
            patterns=[{"exists": None}],
        )
        assert rule.evaluate() == []


class TestNotExists:
    def test_missing_file_matches(self):
        rule = Rule(
            rule_id="nex1",
            files=["/tmp/_warden_nonexistent_12345.txt"],
            patterns=[{"not-exists": None}],
        )
        assert len(rule.evaluate()) == 1

    def test_existing_file_no_match(self):
        path = tmp_text("hello")
        rule = Rule(rule_id="nex2", files=[path], patterns=[{"not-exists": None}])
        assert rule.evaluate() == []
