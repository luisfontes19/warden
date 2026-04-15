from warden.engine.models import Rule

from tests.rule_spec.conftest import tmp_text


class TestMultipleFiles:
    def test_evaluates_all_files(self):
        p1 = tmp_text("alpha content")
        p2 = tmp_text("alpha again")
        rule = Rule(rule_id="mf1", files=[p1, p2], patterns=[{"contains": "alpha"}])
        matches = rule.evaluate()
        assert len(matches) == 2
        assert {m.file for m in matches} == {p1, p2}

    def test_only_matching_files(self):
        p1 = tmp_text("alpha")
        p2 = tmp_text("beta")
        rule = Rule(rule_id="mf2", files=[p1, p2], patterns=[{"contains": "alpha"}])
        matches = rule.evaluate()
        assert len(matches) == 1
        assert matches[0].file == p1

    def test_no_files_match(self):
        p1 = tmp_text("alpha")
        p2 = tmp_text("beta")
        rule = Rule(rule_id="mf3", files=[p1, p2], patterns=[{"contains": "gamma"}])
        assert rule.evaluate() == []
