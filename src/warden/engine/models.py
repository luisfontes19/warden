from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

import logging

from warden.engine.actions import (
    ActionResult,
    apply_json_actions,
    apply_text_actions,
    execute_request_action,
    invoke_code_handler,
)
from warden.engine.file_utils import load_file, resolve_file_path, resolve_filetype
from warden.engine.patterns import match_patterns




class Match:
    """Holds the result of a rule that matched."""

    def __init__(
        self,
        rule_id: str,
        description: str,
        file: str,
        matched_content: Any,
        file_content: Any = None,
    ) -> None:
        self.rule_id = rule_id
        self.description = description
        self.file = file
        self.matched_content = matched_content
        self.file_content = file_content

    def __repr__(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "description": self.description,
            "file": self.file,
            "matched_content": self.matched_content,
            "file_content": self.file_content,
        }


class Rule:
    """Represents a single rule parsed from a rules YAML file."""

    def __init__(
        self,
        rule_id: str,
        files: list[str],
        patterns: list | dict | None = None,
        description: str = "",
        filetype: str | None = None,
        actions: list[dict] | None = None,
        rules_dir: Path | None = None,
        default: str | None = None,
    ) -> None:
        self.rule_id = rule_id
        self.files = files
        self.patterns = patterns
        self.description = description
        self.filetype = filetype
        self.actions: list[dict] = actions or []
        self.rules_dir = rules_dir
        self.default = default

    @classmethod
    def from_dict(cls, data: dict, rules_dir: Path | None = None) -> Rule:
        raw_file = data["file"]
        raw_files = [raw_file] if isinstance(raw_file, str) else list(raw_file)
        files = [resolve_file_path(f) for f in raw_files]

        logging.debug("Resolved paths for rule %s: %s", data["id"], files)

        return cls(
            rule_id=data["id"],
            files=files,
            patterns=data.get("patterns"),
            description=data.get("description", ""),
            filetype=data.get("filetype"),
            actions=data.get("actions") or [],
            rules_dir=rules_dir,
            default=data.get("default"),
        )

    def _make_match(
        self, file_path: str, matched_content: Any, file_content: Any = None,
    ) -> Match:
        return Match(
            rule_id=self.rule_id,
            description=self.description,
            file=file_path,
            matched_content=matched_content,
            file_content=file_content,
        )

    def evaluate_against_file(self, file_path: str) -> list[Match]:
        """Evaluate this rule against its target file. Returns a list of Match objects."""
        if self.patterns is None:
            logging.debug("Rule %r: no patterns, auto-match for %s", self.rule_id, file_path)
            return [self._make_match(file_path, matched_content=None)]

        path = Path(file_path)
        if path.exists():
            content = load_file(path, self.filetype)
            file_content = content
        else:
            logging.debug("Rule %r: file %s does not exist", self.rule_id, file_path)
            content = path
            file_content = None

        filetype = resolve_filetype(path, self.filetype)
        matched, extracted = match_patterns(self.patterns, content, filetype)
        if not matched:
            logging.debug("Rule %r: patterns did not match for %s", self.rule_id, file_path)
            return []

        if isinstance(extracted, list):
            return [
                self._make_match(file_path, item, file_content=file_content)
                for item in extracted
            ]
        return [self._make_match(file_path, extracted, file_content=file_content)]

    def apply_actions(self, matches: list[Match]) -> ActionResult | str | None:
        """Apply rule actions and return the outcome."""
        if not self.actions or not matches:
            return None

        first = matches[0]

        for action in self.actions:
            action_key = next(iter(action))
            logging.debug("Rule %r: applying action '%s'", self.rule_id, action_key)

            if action_key == "code":
                if self.rules_dir is None:
                    raise ValueError(
                        f"Rule {self.rule_id!r}: cannot invoke code handler — rules_dir is not set"
                    )
                invoke_code_handler(action["code"], self.rules_dir, first.file)
                return ActionResult.CODE_HANDLED

            if action_key == "request":
                execute_request_action(action["request"], matches)
                return ActionResult.REQUEST_SENT

            if action_key == "delete-file":
                return ActionResult.FILE_DELETED

        all_matched = [m.matched_content for m in matches]
        file_content = first.file_content

        filetype = resolve_filetype(Path(first.file), self.filetype)
        if filetype == "json":
            return apply_json_actions(file_content, all_matched, self.actions)
        return apply_text_actions(file_content, all_matched, self.actions)

    def evaluate(self) -> list[Match]:
        return [m for f in self.files for m in self.evaluate_against_file(f)]

    def apply_defaults(self) -> None:
        """Create missing files with the default content if `default` is set."""
        if self.default is None:
            return
        for file_path in self.files:
            path = Path(file_path)
            if path.exists():
                continue
            logging.info("Rule %r: creating %s with default content", self.rule_id, file_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(self.default, encoding="utf-8")

    def __repr__(self) -> str:
        return f"Rule(id={self.rule_id!r}, files={self.files!r})"


class RuleFile:
    """Parses a single YAML rules file and exposes its rules."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._rules: list[Rule] = self._parse()

    def _parse(self) -> list[Rule]:
        data = yaml.safe_load(self.path.read_text(encoding="utf-8"))
        rules = [Rule.from_dict(r, rules_dir=self.path.parent) for r in data.get("rules", [])]
        logging.debug("Parsed %d rule(s) from %s", len(rules), self.path)
        return rules

    @property
    def rules(self) -> list[Rule]:
        return list(self._rules)

    def __repr__(self) -> str:
        return f"RuleFile(path={self.path!r}, rules={len(self._rules)})"

