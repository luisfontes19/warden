from pathlib import Path
from unittest.mock import patch

import pytest

from tests.rule_spec.conftest import tmp_text
from warden.engine.actions import ActionResult
from warden.engine.models import Rule


class TestActionCodeAllowed:
    """Tests when code actions are explicitly allowed."""

    @pytest.fixture(autouse=True)
    def _allow_code(self):
        with patch("warden.engine.rules_engine.Configs") as mock:
            mock.instance.allow_code_rules = True
            yield

    def test_handler_invoked(self, tmp_path: Path):
        handler_code = (
            "def handler(filename):\n"
            "    from pathlib import Path\n"
            "    Path(filename).write_text('handled', encoding='utf-8')\n"
        )
        (tmp_path / "handler.py").write_text(handler_code, encoding="utf-8")
        target = tmp_path / "target.txt"
        target.write_text("original", encoding="utf-8")

        rule = Rule(
            rule_id="code1", files=[str(target)],
            patterns=[{"contains": "original"}],
            actions=[{"code": "handler.py"}],
            rules_dir=tmp_path,
        )
        matches = rule.evaluate()
        assert rule.apply_actions(matches) is ActionResult.CODE_HANDLED
        assert target.read_text() == "handled"

    def test_path_traversal_blocked(self, tmp_path: Path):
        rule = Rule(
            rule_id="code2", files=[tmp_text("x")],
            patterns=[{"contains": "x"}],
            actions=[{"code": "../../../etc/passwd"}],
            rules_dir=tmp_path,
        )
        matches = rule.evaluate()
        with pytest.raises(ValueError, match="Path traversal"):
            rule.apply_actions(matches)

    def test_no_rules_dir_raises(self):
        path = tmp_text("test")
        rule = Rule(
            rule_id="code3", files=[path],
            patterns=[{"contains": "test"}],
            actions=[{"code": "handler.py"}],
            rules_dir=None,
        )
        matches = rule.evaluate()
        with pytest.raises(ValueError, match="rules_dir is not set"):
            rule.apply_actions(matches)


class TestActionCodeDisabled:
    """Tests when code actions are not allowed (default)."""

    @pytest.fixture(autouse=True)
    def _disallow_code(self):
        with patch("warden.engine.rules_engine.Configs") as mock:
            mock.instance.allow_code_rules = False
            yield

    def test_handler_not_invoked(self, tmp_path: Path):
        handler_code = (
            "def handler(filename):\n"
            "    from pathlib import Path\n"
            "    Path(filename).write_text('handled', encoding='utf-8')\n"
        )
        (tmp_path / "handler.py").write_text(handler_code, encoding="utf-8")
        target = tmp_path / "target.txt"
        target.write_text("original", encoding="utf-8")

        rule = Rule(
            rule_id="code4", files=[str(target)],
            patterns=[{"contains": "original"}],
            actions=[{"code": "handler.py"}],
            rules_dir=tmp_path,
        )
        matches = rule.evaluate()
        assert rule.apply_actions(matches) is ActionResult.CODE_HANDLED
        assert target.read_text() == "original"
