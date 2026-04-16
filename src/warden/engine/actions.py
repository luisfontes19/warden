from __future__ import annotations

import importlib.util
import json
import logging
from enum import Enum
from pathlib import Path
from typing import Any

import jq
import requests
import logging

from warden import Configs
from warden.engine.templates import build_template_context, render_value




class ActionResult(Enum):
    """Non-content outcomes from Rule.apply_actions."""
    FILE_DELETED = "file_deleted"
    CODE_HANDLED = "code_handled"
    REQUEST_SENT = "request_sent"


def invoke_code_handler(code_path: str, rules_dir: Path, filename: str) -> None:
    """Dynamically load a Python file and call its handler(filename) function."""
    if not Configs.instance.allow_code_rules:
        return logging.warning("Code execution is disabled by config, skipping code handler: %s", code_path)

    rules_dir_resolved = rules_dir.resolve()
    resolved = (rules_dir / code_path).resolve()

    if not str(resolved).startswith(str(rules_dir_resolved) + "/") and resolved != rules_dir_resolved:
        raise ValueError(f"Path traversal detected in code path: {code_path!r}")

    if not resolved.exists():
        raise FileNotFoundError(f"Code handler file not found: {resolved}")

    logging.info("Invoking code handler %s for %s", resolved, filename)

    spec = importlib.util.spec_from_file_location("_warden_rule_handler", resolved)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {resolved}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]

    if not hasattr(module, "handler"):
        raise AttributeError(f"Code handler {resolved} must define a 'handler(filename)' function")

    module.handler(filename)


def apply_text_actions(
    file_content: Any, matched_contents: list[Any], actions: list[dict],
) -> str:
    content = file_content if file_content is not None else ""
    needles = [str(n) for n in matched_contents if n is not None]
    logging.debug("Applying %d text action(s) to %d needle(s)", len(actions), len(needles))

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


def apply_json_actions(
    file_content: Any, matched_contents: list[Any], actions: list[dict],
) -> str:
    content = file_content if file_content is not None else {}
    matched_content = matched_contents[0] if len(matched_contents) == 1 else matched_contents
    logging.debug("Applying %d JSON action(s)", len(actions))

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


def execute_request_action(config: dict, matches: list) -> requests.Response:
    """Execute an HTTP request action with template rendering."""
    ctx = build_template_context(matches)
    rendered = render_value(config, ctx)

    url = rendered.get("url")
    if not url:
        raise ValueError("request action requires a 'url' field")

    method = rendered.get("method", "POST").upper()
    headers = rendered.get("headers") or {}
    body = rendered.get("body")

    logging.info("Rule %r: %s %s", matches[0].rule_id, method, url)

    response = requests.request(
        method=method,
        url=url,
        headers=headers,
        data=body,
        timeout=30,
    )
    response.raise_for_status()

    logging.info("Rule %r: response %s", matches[0].rule_id, response.status_code)
    return response
