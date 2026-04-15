from __future__ import annotations

import importlib.util
import json
import logging
import os
import re
from enum import Enum
from pathlib import Path
from typing import Any

import jq
import requests
import yaml
from jinja2 import BaseLoader, Environment

from warden.configs import Configs

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def _resolve_file_path(raw: str) -> str:
    """Expand ~ to the real user's home and resolve to an absolute path."""
    if raw.startswith("~/"):
        raw = os.getlogin() + raw[1:]
    return str(Path(raw).resolve())


# ---------------------------------------------------------------------------
# Action result
# ---------------------------------------------------------------------------

class ActionResult(Enum):
    """Non-content outcomes from Rule.apply_actions."""
    FILE_DELETED = "file_deleted"
    CODE_HANDLED = "code_handled"
    REQUEST_SENT = "request_sent"


# ---------------------------------------------------------------------------
# RuleMatch
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Rule
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
        rules_dir: Path | None = None,
    ) -> None:
        self.rule_id = rule_id
        self.files = files
        self.patterns = patterns
        self.description = description
        self.filetype = filetype
        self.actions: list[dict] = actions or []
        self.rules_dir = rules_dir

    @classmethod
    def from_dict(cls, data: dict, rules_dir: Path | None = None) -> Rule:
        raw_file = data["file"]
        raw_files = [raw_file] if isinstance(raw_file, str) else list(raw_file)
        files = [_resolve_file_path(f) for f in raw_files]

        logging.debug(f"Resolved paths for rule: {files}")

        return cls(
            rule_id=data["id"],
            files=files,
            patterns=data.get("patterns"),
            description=data.get("description", ""),
            filetype=data.get("filetype"),
            actions=data.get("actions") or [],
            rules_dir=rules_dir,
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
            return [self._make_match(file_path, matched_content=None)]

        path = Path(file_path)
        if path.exists():
            content = _load_file(path, self.filetype)
            file_content = content
        else:
            content = path
            file_content = None

        matched, extracted = _match_patterns(self.patterns, content)
        if not matched:
            return []

        if isinstance(extracted, list):
            return [
                self._make_match(file_path, item, file_content=file_content)
                for item in extracted
            ]
        return [self._make_match(file_path, extracted, file_content=file_content)]

    def apply_actions(self, matches: list[Match]) -> ActionResult | str | None:
        """Apply rule actions and return the outcome.

        Returns:
            ActionResult.FILE_DELETED — file should be deleted
            ActionResult.CODE_HANDLED — code handler ran; no further I/O needed
            str — new file content to write
            None — no actions defined
        """
        if not self.actions or not matches:
            return None

        first = matches[0]

        for action in self.actions:
            action_key = next(iter(action))

            if action_key == "code":
                if self.rules_dir is None:
                    raise ValueError(
                        f"Rule {self.rule_id!r}: cannot invoke code handler — rules_dir is not set"
                    )
                _invoke_code_handler(action["code"], self.rules_dir, first.file)
                return ActionResult.CODE_HANDLED

            if action_key == "request":
                _execute_request_action(action["request"], matches)
                return ActionResult.REQUEST_SENT

            if action_key == "delete-file":
                return ActionResult.FILE_DELETED

        all_matched = [m.matched_content for m in matches]
        file_content = first.file_content

        filetype = _resolve_filetype(Path(first.file), self.filetype)
        if filetype == "json":
            return _apply_json_actions(file_content, all_matched, self.actions)
        return _apply_text_actions(file_content, all_matched, self.actions)

    def evaluate(self) -> list[Match]:
        return [m for f in self.files for m in self.evaluate_against_file(f)]

    def __repr__(self) -> str:
        return f"Rule(id={self.rule_id!r}, files={self.files!r})"


# ---------------------------------------------------------------------------
# RuleFile
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
# RuleEngine
# ---------------------------------------------------------------------------

class RuleEngine:
    """Loads rules and evaluates / enforces them against files."""

    def __init__(self, folder: str | None = None, rule_files: list[str] | None = None) -> None:
        self.rules: list[Rule] = []
        self.rules.extend(self._load_rules_from_folder(Configs.configs.rules_dir))
        if folder:
            self.rules.extend(self._load_rules_from_folder(folder))
        for f in (rule_files or []):
            self.rules.extend(self._load_rules_from_file(f))

    @staticmethod
    def _load_rules_from_file(path: str | Path) -> list[Rule]:
        try:
            return RuleFile(path).rules
        except Exception as exc:
            logger.error("Error loading %s: %s", path, exc)
            return []

    def _load_rules_from_folder(self, folder: str | Path) -> list[Rule]:
        rules: list[Rule] = []
        for yml in Path(folder).glob("*.yml"):
            rules.extend(self._load_rules_from_file(yml))
        return rules

    def _rules_for_file(self, file: str) -> list[Rule]:
        resolved = _resolve_file_path(file)
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
                continue

            result = rule.apply_actions(matches)
            if isinstance(result, ActionResult):
                if result is ActionResult.FILE_DELETED:
                    Path(matches[0].file).unlink(missing_ok=True)
            elif result is not None:
                Path(matches[0].file).write_text(result, encoding="utf-8")

            results.extend(matches)
        return results

    def monitoring_files(self) -> list[str]:
        """Return a list of all files that are targeted by rules."""
        return list({f for rule in self.rules for f in rule.files})


# ---------------------------------------------------------------------------
# File loading
# ---------------------------------------------------------------------------

def _resolve_filetype(path: Path, filetype: str | None) -> str:
    return filetype or path.suffix.lstrip(".").lower() or "text"


def _load_file(path: Path, filetype: str | None) -> Any:
    resolved = _resolve_filetype(path, filetype)
    if resolved == "json":
        return json.loads(path.read_bytes())
    if resolved == "binary":
        return path.read_bytes()
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Code handler
# ---------------------------------------------------------------------------

def _invoke_code_handler(code_path: str, rules_dir: Path, filename: str) -> None:
    """Dynamically load a Python file and call its handler(filename) function."""
    rules_dir_resolved = rules_dir.resolve()
    resolved = (rules_dir / code_path).resolve()

    if not str(resolved).startswith(str(rules_dir_resolved) + "/") and resolved != rules_dir_resolved:
        raise ValueError(f"Path traversal detected in code path: {code_path!r}")

    if not resolved.exists():
        raise FileNotFoundError(f"Code handler file not found: {resolved}")

    spec = importlib.util.spec_from_file_location("_warden_rule_handler", resolved)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {resolved}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]

    if not hasattr(module, "handler"):
        raise AttributeError(f"Code handler {resolved} must define a 'handler(filename)' function")

    module.handler(filename)


# ---------------------------------------------------------------------------
# Pattern matching — leaf matchers
# ---------------------------------------------------------------------------

def _check_jq(content: Any, value: Any) -> tuple[bool, Any]:
    result = jq.first(value, content)
    return bool(result), result if bool(result) else content


def _check_containment(content: Any, value: Any) -> tuple[bool, Any]:
    """Check whether *content* contains *value*. Returns (found, needle)."""
    if isinstance(content, bytes):
        needle = value.encode() if isinstance(value, str) else value
        return needle in content, needle
    if isinstance(content, str):
        needle = str(value)
        return needle in content, needle
    if isinstance(content, (list, dict)):
        return value in content, value
    needle = str(value)
    return needle in str(content), needle


def _check_equals(content: Any, value: Any) -> tuple[bool, Any]:
    return content == value, content


def _check_existence(content: Any, _value: Any) -> tuple[bool, Any]:
    if isinstance(content, Path):
        return content.exists(), str(content)
    return True, content


def _check_regex(content: Any, value: Any) -> tuple[bool, Any]:
    target = content if isinstance(content, str) else str(content)
    m = re.search(value, target)
    return bool(m), m.group(0) if m else content


_LEAF_MATCHERS: dict[str, Any] = {
    "jq": _check_jq,
    "contains": _check_containment,
    "equals": _check_equals,
    "exists": _check_existence,
    "match": _check_regex,
}

_NEGATED_MATCHERS: dict[str, str] = {
    "not-contains": "contains",
    "not-equals": "equals",
    "not-exists": "exists",
}


# ---------------------------------------------------------------------------
# Pattern matching — evaluation
# ---------------------------------------------------------------------------

def _match_patterns(patterns: list | dict, content: Any) -> tuple[bool, Any]:
    """Evaluate a pattern node (or AND-ed list) against content."""
    if isinstance(patterns, dict):
        return _match_pattern(patterns, content)

    if isinstance(patterns, list):
        extracted = content
        for p in patterns:
            matched, val = _match_pattern(p, content)
            if not matched:
                return False, content
            extracted = val
        return True, extracted

    raise ValueError(f"Unsupported patterns structure: {type(patterns)}")


def _match_pattern(pattern: dict, content: Any) -> tuple[bool, Any]:
    """Evaluate a single pattern node against content."""
    [(key, value)] = pattern.items()

    if key == "or":
        return _match_or(value, content)

    if key == "and":
        return _match_and(value, content)

    if key in _NEGATED_MATCHERS:
        matched, _ = _LEAF_MATCHERS[_NEGATED_MATCHERS[key]](content, value)
        extracted = str(content) if isinstance(content, Path) else content
        return not matched, extracted

    if key in _LEAF_MATCHERS:
        return _LEAF_MATCHERS[key](content, value)

    raise ValueError(f"Unknown pattern type: '{key}'")


def _match_or(sub_patterns: list[dict], content: Any) -> tuple[bool, Any]:
    matched_vals = []
    for sub in sub_patterns:
        matched, val = _match_pattern(sub, content)
        if matched:
            matched_vals.append(val)
    if not matched_vals:
        return False, content
    return True, matched_vals[0] if len(matched_vals) == 1 else matched_vals


def _match_and(sub_patterns: list[dict], content: Any) -> tuple[bool, Any]:
    all_vals: list = []
    for sub in sub_patterns:
        matched, val = _match_pattern(sub, content)
        if not matched:
            return False, content
        if isinstance(val, list):
            all_vals.extend(val)
        else:
            all_vals.append(val)
    return True, all_vals[0] if len(all_vals) == 1 else all_vals


# ---------------------------------------------------------------------------
# Action application
# ---------------------------------------------------------------------------

def _apply_text_actions(
    file_content: Any, matched_contents: list[Any], actions: list[dict],
) -> str:
    content = file_content if file_content is not None else ""
    needles = [str(n) for n in matched_contents if n is not None]

    for action in actions:
        [(key, value)] = action.items()

        if key in ("delete", "replace"):
            replacement = "" if key == "delete" else (str(value) if value is not None else "")
            for needle in needles:
                content = content.replace(needle, replacement)
        elif key == "add":
            content += str(value)
        else:
            raise ValueError(f"Unknown text action: '{key}'")

    return content


def _apply_json_actions(
    file_content: Any, matched_contents: list[Any], actions: list[dict],
) -> str:
    content = file_content if file_content is not None else {}
    matched_content = matched_contents[0] if len(matched_contents) == 1 else matched_contents

    for action in actions:
        [(key, value)] = action.items()

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
                raise ValueError(f"JSON replace must have 'jq' or 'str', got: {list(value.keys())}")
        else:
            raise ValueError(f"JSON replace value must be string, dict, or null, got: {type(value)}")

    return json.dumps(content, indent=2)


# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------

def _json_filter(value: Any) -> str:
    """Jinja2 global: serialise any value to a JSON string."""
    if isinstance(value, Match):
        return json.dumps(value.to_dict())
    if isinstance(value, list) and value and isinstance(value[0], Match):
        return json.dumps([m.to_dict() for m in value])
    return json.dumps(value)


_jinja_env = Environment(
    loader=BaseLoader(),
    variable_start_string="${{",
    variable_end_string="}}",
    autoescape=False,
)
_jinja_env.globals["json"] = _json_filter


def _build_template_context(matches: list[Match]) -> dict[str, Any]:
    """Build the Jinja2 context dict exposed to action placeholders."""
    first = matches[0]
    all_matched = [m.matched_content for m in matches]
    return {
        "rule_id": first.rule_id,
        "description": first.description,
        "file": first.file,
        "matched_content": all_matched[0] if len(all_matched) == 1 else all_matched,
        "file_content": first.file_content,
        "matches": matches,
    }


def _render_template(value: str, context: dict[str, Any]) -> str:
    """Render a string containing ${{…}} placeholders using Jinja2."""
    if not isinstance(value, str):
        return value
    if "${{" not in value:
        return value
    return _jinja_env.from_string(value).render(context)


def _render_value(value: Any, context: dict[str, Any]) -> Any:
    """Recursively render placeholders in strings, dicts, and lists."""
    if isinstance(value, str):
        return _render_template(value, context)
    if isinstance(value, dict):
        return {k: _render_value(v, context) for k, v in value.items()}
    if isinstance(value, list):
        return [_render_value(item, context) for item in value]
    return value


# ---------------------------------------------------------------------------
# Request action
# ---------------------------------------------------------------------------

def _execute_request_action(config: dict, matches: list[Match]) -> requests.Response:
    """Execute an HTTP request action with template rendering."""
    ctx = _build_template_context(matches)
    rendered = _render_value(config, ctx)

    url = rendered.get("url")
    if not url:
        raise ValueError("request action requires a 'url' field")

    method = rendered.get("method", "POST").upper()
    headers = rendered.get("headers") or {}
    body = rendered.get("body")

    logger.info("Rule %r: %s %s", matches[0].rule_id, method, url)

    response = requests.request(
        method=method,
        url=url,
        headers=headers,
        data=body,
        timeout=30,
    )
    response.raise_for_status()

    logger.info("Rule %r: response %s", matches[0].rule_id, response.status_code)
    return response

