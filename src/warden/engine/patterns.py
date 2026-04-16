from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any
import logging

import jq



_LEAF_MATCHERS: dict[str, Any] = {
    "jq": None,  # set below
    "contains": None,
    "equals": None,
    "exists": None,
    "match": None,
}

_NEGATED_MATCHERS: dict[str, str] = {
    "not-contains": "contains",
    "not-equals": "equals",
    "not-exists": "exists",
}


def _check_jq(content: Any, value: Any) -> tuple[bool, Any]:
    results = jq.all(value, content)
    truthy = [r for r in results if r]
    if not truthy:
        return False, content
    if len(truthy) == 1:
        return True, truthy[0]
    return True, truthy


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


_LEAF_MATCHERS["jq"] = _check_jq
_LEAF_MATCHERS["contains"] = _check_containment
_LEAF_MATCHERS["equals"] = _check_equals
_LEAF_MATCHERS["exists"] = _check_existence
_LEAF_MATCHERS["match"] = _check_regex


def match_patterns(patterns: list | dict, content: Any, filetype: str = "text") -> tuple[bool, Any]:
    """Evaluate a pattern node (or AND-ed list) against content."""
    if isinstance(patterns, dict):
        return _match_pattern(patterns, content, filetype)

    if isinstance(patterns, list):
        extracted = content
        for p in patterns:
            matched, val = _match_pattern(p, content, filetype)
            if not matched:
                return False, content
            extracted = val
        return True, extracted

    raise ValueError(f"Unsupported patterns structure: {type(patterns)}")


def _match_pattern(pattern: dict, content: Any, filetype: str = "text") -> tuple[bool, Any]:
    """Evaluate a single pattern node against content."""
    [(key, value)] = pattern.items()

    if key == "or":
        return _match_or(value, content, filetype)

    if key == "and":
        return _match_and(value, content, filetype)

    if key == "nested":
        return _match_nested(value, content, filetype)

    if key in _NEGATED_MATCHERS:
        matched, _ = _LEAF_MATCHERS[_NEGATED_MATCHERS[key]](content, value)
        extracted = str(content) if isinstance(content, Path) else content
        return not matched, extracted

    if key in _LEAF_MATCHERS:
        return _LEAF_MATCHERS[key](content, value)

    raise ValueError(f"Unknown pattern type: '{key}'")


def _match_or(sub_patterns: list[dict], content: Any, filetype: str) -> tuple[bool, Any]:
    matched_vals = []
    for sub in sub_patterns:
        matched, val = _match_pattern(sub, content, filetype)
        if matched:
            matched_vals.append(val)
    if not matched_vals:
        return False, content
    return True, matched_vals[0] if len(matched_vals) == 1 else matched_vals


def _match_and(sub_patterns: list[dict], content: Any, filetype: str) -> tuple[bool, Any]:
    all_vals: list = []
    for sub in sub_patterns:
        matched, val = _match_pattern(sub, content, filetype)
        if not matched:
            return False, content
        if isinstance(val, list):
            all_vals.extend(val)
        else:
            all_vals.append(val)
    return True, all_vals[0] if len(all_vals) == 1 else all_vals


def _match_nested(sub_patterns: list[dict], content: Any, filetype: str) -> tuple[bool, Any]:
    """Chain patterns: each pattern's match is re-parsed and fed as input to the next."""

    from warden.engine.file_utils import parse_content

    current = content
    for sub in sub_patterns:
        matched, val = _match_pattern(sub, current, filetype)
        if not matched:
            logging.debug("Nested chain broke at pattern %s", sub)
            return False, content
        try:
            current = parse_content(val, filetype)
        except (ValueError, UnicodeDecodeError):
            current = val
    return True, current
