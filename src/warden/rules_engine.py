from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from warden.configs import Configs

# Sentinels returned by apply_actions
FILE_DELETED = "__FILE_DELETED__"
CODE_HANDLED = "__CODE_HANDLED__"

import jq
import yaml

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# RuleMatch — result of a fired rule
# ---------------------------------------------------------------------------

class RuleMatch:
    """Holds the result of a rule that matched."""

    def __init__(self, rule_id: str, description: str, file: str, matched_content: Any) -> None:
        self.rule_id = rule_id
        self.description = description
        self.file = file
        self.matched_content = matched_content

    def __repr__(self) -> str:
        return json.dumps({
            "rule_id": self.rule_id,
            "description": self.description,
            "file": self.file,
            "matched_content": self.matched_content,
        }, indent=2)


# ---------------------------------------------------------------------------
# Rule — a single evaluatable rule
# ---------------------------------------------------------------------------

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
        code: str | None = None,
        rules_dir: Path | None = None,
    ) -> None:
        self.rule_id = rule_id
        self.files = files
        self.patterns = patterns
        self.description = description
        self.filetype = filetype
        self.actions: list[dict] = actions or []
        self.code = code
        self.rules_dir = rules_dir

    @classmethod
    def from_dict(cls, data: dict, rules_dir: Path | None = None) -> Rule:
        raw_file = data["file"]
        files = [raw_file] if isinstance(raw_file, str) else list(raw_file)
        return cls(
            rule_id=data["id"],
            files=files,
            patterns=data.get("patterns"),
            description=data.get("description", ""),
            filetype=data.get("filetype"),
            actions=data.get("actions") or [],
            code=data.get("code"),
            rules_dir=rules_dir,
        )

    def apply_actions(self, match: RuleMatch) -> str | None:
        """Plan all actions and return the new file content, or None if no actions."""
        if self.code is not None:
            if self.rules_dir is None:
                raise ValueError(f"Rule {self.rule_id!r}: cannot invoke code handler — rules_dir is not set")
            _invoke_code_handler(self.code, self.rules_dir, match.file)
            return CODE_HANDLED

        if not self.actions:
            return None
        # delete-file is a file-level action; handle before content actions

        for action in self.actions:
            if next(iter(action)) == "delete-file":
                return FILE_DELETED
        path = Path(match.file)
        resolved = self.filetype or path.suffix.lstrip(".").lower()
        if resolved == "json":
            content = json.loads(path.read_bytes())
            result = _plan_actions_json(content, self.actions, match.matched_content)
            return json.dumps(result, indent=2)
        else:
            text = path.read_text(encoding="utf-8") if path.exists() else ""
            return _plan_actions_text(text, match.matched_content, self.actions)

    def evaluate_against_file(self, file_path: str) -> RuleMatch | None:
        """Evaluate this rule against its target file. Returns a RuleMatch or None."""
        path = Path(file_path)
        if self.patterns is None:
            if self.code is not None:
                # code-only rule: always triggers; handler handles all logic
                return RuleMatch(rule_id=self.rule_id, description=self.description, file=file_path, matched_content=None)
            return None
        if not path.exists():
            # Pass the Path so that exists/not-exists patterns can check it
            matched, extracted = _match_patterns(self.patterns, path)
            if matched:
                return RuleMatch(rule_id=self.rule_id, description=self.description, file=file_path, matched_content=extracted)
            return None

        content = _load_file(path, self.filetype)
        matched, extracted = _match_patterns(self.patterns, content)

        if matched:
            return RuleMatch(rule_id=self.rule_id, description=self.description, file=file_path, matched_content=extracted)
        return None

    def evaluate(self) -> list[RuleMatch]:
        return [m for f in self.files if (m := self.evaluate_against_file(f)) is not None]

    def __repr__(self) -> str:
        return f"Rule(id={self.rule_id!r}, files={self.files!r})"


# ---------------------------------------------------------------------------
# RuleFile — parses a YAML file into Rule objects
# ---------------------------------------------------------------------------

class RuleFile:
    """Parses a single YAML rules file and exposes its rules."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._rules: list[Rule] = self._parse()

    def _parse(self) -> list[Rule]:
        data = yaml.safe_load(self.path.read_text(encoding="utf-8"))
        return [Rule.from_dict(r, rules_dir=self.path.parent) for r in data.get("rules", [])]

    @property
    def rules(self) -> list[Rule]:
        return list(self._rules)

    def __repr__(self) -> str:
        return f"RuleFile(path={self.path!r}, rules={len(self._rules)})"


# ---------------------------------------------------------------------------
# RuleEngine — orchestrates loading and evaluation
# ---------------------------------------------------------------------------

class RuleEngine:
    """Stores Rule objects and evaluates them."""

    def __init__(self, folder: str|None = None, rule_files: list[str]|None = None) -> None:
        self.rules: list[Rule] = []

        self.rules.extend(self._load_rules_from_folder(Configs.configs.rules_dir))

        if folder:
            self.rules.extend(self._load_rules_from_folder(folder))

        for f in (rule_files or []):
            try:
                self.rules.extend(RuleFile(f).rules)
            except Exception as exc:
                logger.error("Error loading %s: %s", f, exc)


    def _load_rules_from_folder(self, folder: str|Path) -> list[Rule]:
        rules = []
        for yml in Path(folder).glob("*.yml"):
            try:
                rules.extend(RuleFile(yml).rules)
            except Exception as exc:
                logger.error("Error loading %s: %s", yml, exc)

        return rules

    def run(self) -> list[RuleMatch]:
        """Evaluate every rule and return all matches."""
        return [m for rule in self.rules for m in rule.evaluate()]

    def evaluate_file(self, file: str) -> list[RuleMatch]:
        """Evaluate only rules that target the specified file."""
        results = []
        for rule in self.rules:
            if file in rule.files:
                m = rule.evaluate_against_file(file)
                if m:
                    results.append(m)
        return results

    def enforce(self, file: str) -> list[RuleMatch]:
        """Evaluate rules targeting file, apply actions, and write changes to disk."""
        results = []
        for rule in self.rules:
            if file not in rule.files: continue

            m = rule.evaluate_against_file(file)
            if not m: continue

            new_content = rule.apply_actions(m)
            if new_content == FILE_DELETED:
                Path(m.file).unlink(missing_ok=True)
            elif new_content is not None and new_content != CODE_HANDLED:
                Path(m.file).write_text(new_content, encoding="utf-8")
            results.append(m)
        return results

    def monitoring_files(self) -> list[str]:
        """Return a list of all files that are targeted by rules."""
        return list(set(f for rule in self.rules for f in rule.files))

# ---------------------------------------------------------------------------
# Pattern matching helpers (module-level, used by Rule)
# ---------------------------------------------------------------------------

def _invoke_code_handler(code_path: str, rules_dir: Path, filename: str) -> None:
    """Dynamically load a Python handler file and invoke its handler(filename) function."""
    import importlib.util

    # Prevent path traversal: resolve and ensure it stays inside rules_dir
    rules_dir_resolved = rules_dir.resolve()
    resolved = (rules_dir / code_path).resolve()

    if not str(resolved).startswith(str(rules_dir_resolved) + "/") and resolved != rules_dir_resolved:
        raise ValueError(f"Path traversal detected in code path: {code_path!r}")

    spec = importlib.util.spec_from_file_location("_warden_rule_handler", resolved)

    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {resolved}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]

    if not hasattr(module, "handler"):
        raise AttributeError(f"Code handler {resolved} must define a 'handler(filename)' function")

    module.handler(filename)


def _load_file(path: Path, filetype: str | None) -> Any:
    resolved = filetype or path.suffix.lstrip(".").lower()
    if resolved == "json":
        return json.loads(path.read_bytes())
    if resolved == "binary":
        return path.read_bytes()
    # "text" or any unknown extension
    return path.read_text(encoding="utf-8")


def _match_patterns(patterns: list | dict, content: Any) -> tuple[bool, Any]:
    if isinstance(patterns, list):
        extracted = content
        for p in patterns:
            matched, val = _match_pattern(p, content)
            if not matched:
                return False, content
            extracted = val
        return True, extracted
    if isinstance(patterns, dict):
        return _match_pattern(patterns, content)
    raise ValueError(f"Unsupported patterns structure: {type(patterns)}")


def _match_pattern(pattern: dict, content: Any) -> tuple[bool, Any]:
    if len(pattern) != 1:
        raise ValueError(f"Pattern node must have exactly one key, got: {list(pattern.keys())}")

    key, value = next(iter(pattern.items()))

    if key == "jq":
        result = jq.first(value, content)
        return bool(result), result if bool(result) else content

    if key == "contains":
        if isinstance(content, bytes):
            needle = value.encode() if isinstance(value, str) else value
            return needle in content, needle
        if isinstance(content, str):
            needle_s = str(value)
            return needle_s in content, needle_s
        if isinstance(content, (list, dict)):
            return value in content, value
        return str(value) in str(content), str(value)

    if key == "equals":
        return content == value, content

    if key == "not-equals":
        return content != value, content

    if key == "not-contains":
        if isinstance(content, bytes):
            needle = value.encode() if isinstance(value, str) else value
            return needle not in content, content
        if isinstance(content, str):
            return str(value) not in content, content
        if isinstance(content, (list, dict)):
            return value not in content, content
        return str(value) not in str(content), content

    if key == "exists":
        if isinstance(content, Path):
            return content.exists(), str(content)
        return True, content  # content was loaded from the file, so it exists

    if key == "not-exists":
        if isinstance(content, Path):
            return not content.exists(), str(content)
        return False, content  # content was loaded from the file, so it exists

    if key == "match":
        target = content if isinstance(content, str) else str(content)
        m = re.search(value, target)
        return bool(m), m.group(0) if m else content

    if key == "or":
        matched_vals = []
        for sub in value:
            matched, val = _match_pattern(sub, content)
            if matched:
                matched_vals.append(val)
        if matched_vals:
            return True, matched_vals[0] if len(matched_vals) == 1 else matched_vals
        return False, content

    if key == "and":
        all_vals: list = []
        for sub in value:
            matched, val = _match_pattern(sub, content)
            if not matched:
                return False, content
            if isinstance(val, list):
                all_vals.extend(val)
            else:
                all_vals.append(val)
        return True, all_vals[0] if len(all_vals) == 1 else all_vals

    raise ValueError(f"Unknown pattern type: '{key}'")


# ---------------------------------------------------------------------------
# Action planners — pure functions, no file I/O
# ---------------------------------------------------------------------------

def _plan_actions_text(text: str, matched_content: Any, actions: list[dict]) -> str:
    if isinstance(matched_content, list):
        needles = [s if isinstance(s, str) else str(s) for s in matched_content]
    else:
        needles = [matched_content if isinstance(matched_content, str) else str(matched_content)]
    for action in actions:
        if len(action) != 1:
            raise ValueError(f"Action node must have exactly one key, got: {list(action.keys())}")
        key, value = next(iter(action.items()))
        if key == "delete":
            for needle in needles:
                text = text.replace(needle, "")
        elif key == "replace":
            for needle in needles:
                text = text.replace(needle, str(value) if value is not None else "")
        elif key == "add":
            text = text + str(value)
        else:
            raise ValueError(f"Unknown text action: '{key}'")
    return text


def _plan_actions_json(content: Any, actions: list[dict], matched_content: Any = None) -> Any:
    for action in actions:
        if len(action) != 1:
            raise ValueError(f"Action node must have exactly one key, got: {list(action.keys())}")
        key, value = next(iter(action.items()))
        if key != "replace":
            raise ValueError(f"JSON files only support 'replace' actions, got: '{key}'")
        if value is None:
            content = matched_content
        elif isinstance(value, str):
            content = json.loads(value)
        elif isinstance(value, dict):
            if "jq" in value:
                content = jq.first(value["jq"], content)
            elif "str" in value:
                content = json.loads(value["str"])
            else:
                raise ValueError(f"JSON replace action must have 'jq' or 'str' key, got: {list(value.keys())}")
        else:
            raise ValueError(f"JSON replace action value must be a string or object, got: {type(value)}")
    return content

