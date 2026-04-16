from pathlib import Path

from warden.engine.models import Rule


class TestDefault:
    def test_creates_file_when_missing(self, tmp_path: Path):
        target = tmp_path / "config.txt"
        rule = Rule(
            rule_id="default1",
            files=[str(target)],
            default="hello world",
        )
        assert not target.exists()
        rule.apply_defaults()
        assert target.exists()
        assert target.read_text() == "hello world"

    def test_does_not_overwrite_existing(self, tmp_path: Path):
        target = tmp_path / "config.txt"
        target.write_text("existing", encoding="utf-8")
        rule = Rule(
            rule_id="default2",
            files=[str(target)],
            default="new content",
        )
        rule.apply_defaults()
        assert target.read_text() == "existing"

    def test_no_default_is_noop(self, tmp_path: Path):
        target = tmp_path / "config.txt"
        rule = Rule(
            rule_id="default3",
            files=[str(target)],
        )
        rule.apply_defaults()
        assert not target.exists()

    def test_creates_parent_directories(self, tmp_path: Path):
        target = tmp_path / "deep" / "nested" / "config.txt"
        rule = Rule(
            rule_id="default4",
            files=[str(target)],
            default="nested default",
        )
        rule.apply_defaults()
        assert target.exists()
        assert target.read_text() == "nested default"

    def test_default_then_patterns_evaluate(self, tmp_path: Path):
        target = tmp_path / "config.txt"
        rule = Rule(
            rule_id="default5",
            files=[str(target)],
            default="debug=true",
            patterns=[{"contains": "debug"}],
            actions=[{"replace": "debug=false"}],
        )
        rule.apply_defaults()
        matches = rule.evaluate()
        assert len(matches) == 1
        assert matches[0].matched_content == "debug"

        result = rule.apply_actions(matches)
        assert result == "debug=false=true"
