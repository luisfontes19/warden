from __future__ import annotations

import logging
from pathlib import Path


from warden.configs import Configs

from warden.engine.actions import (
    ActionResult,
)
from warden.engine.file_utils import resolve_file_path

from warden.configs import Path
from warden.engine.file_utils import resolve_file_path
from warden.engine.models import Match, Rule, RuleFile


class RuleEngine:
    """Loads rules and evaluates / enforces them against files."""

    def __init__(self, folder: str | None = None, rule_files: list[str] | None = None) -> None:
        self.rules: list[Rule] = []
        self.rules.extend(self._load_rules_from_folder(Configs.instance.rules_dir))
        if folder:
            self.rules.extend(self._load_rules_from_folder(folder))
        for f in (rule_files or []):
            self.rules.extend(self._load_rules_from_file(f))
        logging.info("Loaded %d rule(s)", len(self.rules))

    @staticmethod
    def _load_rules_from_file(path: str | Path) -> list[Rule]:
        try:
            return RuleFile(path).rules
        except Exception as exc:
            logging.error("Error loading %s: %s", path, exc)
            return []

    def _load_rules_from_folder(self, folder: str | Path) -> list[Rule]:
        rules: list[Rule] = []
        for yml in Path(folder).glob("*.yml"):
            rules.extend(self._load_rules_from_file(yml))
        return rules

    def _rules_for_file(self, file: str) -> list[Rule]:
        resolved = resolve_file_path(file)
        return [rule for rule in self.rules if resolved in rule.files]

    def run(self) -> list[Match]:
        """Evaluate every rule and return all matches."""
        return [m for rule in self.rules for m in rule.evaluate()]

    def evaluate_file(self, file: str) -> list[Match]:
        """Evaluate only rules that target the specified file."""
        return [
            m
            for rule in self._rules_for_file(file)
            for m in rule.evaluate_against_file(file)
        ]

    def enforce(self, file: str) -> list[Match]:
        """Evaluate rules targeting file, apply actions, and write changes to disk."""
        results: list[Match] = []
        for rule in self._rules_for_file(file):
            matches = rule.evaluate_against_file(file)
            if not matches:
                logging.debug("Rule %r: no match for %s", rule.rule_id, file)
                continue

            logging.info("Rule %r: %d match(es) on %s", rule.rule_id, len(matches), file)

            result = rule.apply_actions(matches)
            if isinstance(result, ActionResult):
                if result is ActionResult.FILE_DELETED:
                    logging.info("Rule %r: deleting %s", rule.rule_id, file)
                    Path(matches[0].file).unlink(missing_ok=True)
                else:
                    logging.info("Rule %r: action result %s", rule.rule_id, result.value)
            elif result is not None:
                logging.info("Rule %r: writing updated content to %s", rule.rule_id, file)
                Path(matches[0].file).write_text(result, encoding="utf-8")

            results.extend(matches)
        return results

    def monitoring_files(self) -> list[str]:
        """Return a list of all files that are targeted by rules."""
        return list({f for rule in self.rules for f in rule.files})
