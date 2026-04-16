"""Tests for inline rules injection from managed policies into the rules engine."""
from __future__ import annotations

import base64

import yaml

from tests.rule_spec.conftest import tmp_text
from warden.configs import Configs
from warden.engine.rules_engine import RuleEngine


def _encode_rule(rule_yaml: str) -> str:
    return base64.b64encode(rule_yaml.encode("utf-8")).decode("utf-8")


class TestInlineRules:
    def test_inline_rules_loaded_into_engine(self):
        path = tmp_text("hello world")
        rule_content = yaml.dump({
            "rules": [{
                "id": "inline-1",
                "file": path,
                "patterns": [{"contains": "hello"}],
            }]
        })
        encoded = _encode_rule(rule_content)

        original_handler = Configs.instance.policyHandler
        original_inline = original_handler.inline_rules
        try:
            original_handler.inline_rules = [encoded]
            engine = RuleEngine()
            inline = [r for r in engine.rules if r.rule_id == "inline-1"]
            assert len(inline) == 1

            matches = engine.evaluate_file(path)
            assert any(m.rule_id == "inline-1" for m in matches)
        finally:
            original_handler.inline_rules = original_inline

    def test_multiple_inline_rules(self):
        path = tmp_text("secret key")
        rules_a = yaml.dump({
            "rules": [{
                "id": "inline-a",
                "file": path,
                "patterns": [{"contains": "secret"}],
            }]
        })
        rules_b = yaml.dump({
            "rules": [{
                "id": "inline-b",
                "file": path,
                "patterns": [{"contains": "key"}],
            }]
        })

        original_handler = Configs.instance.policyHandler
        original_inline = original_handler.inline_rules
        try:
            original_handler.inline_rules = [_encode_rule(rules_a), _encode_rule(rules_b)]
            engine = RuleEngine()
            ids = {r.rule_id for r in engine.rules}
            assert "inline-a" in ids
            assert "inline-b" in ids
        finally:
            original_handler.inline_rules = original_inline

    def test_no_inline_rules(self):
        original_handler = Configs.instance.policyHandler
        original_inline = original_handler.inline_rules
        try:
            original_handler.inline_rules = None
            engine = RuleEngine()
            # Should not crash, just no inline rules loaded
            assert engine.rules is not None
        finally:
            original_handler.inline_rules = original_inline

    def test_invalid_base64_skipped(self):
        original_handler = Configs.instance.policyHandler
        original_inline = original_handler.inline_rules
        try:
            original_handler.inline_rules = ["not-valid-base64!!!"]
            engine = RuleEngine()
            # Should not crash, invalid rules are skipped
            assert engine.rules is not None
        finally:
            original_handler.inline_rules = original_inline
