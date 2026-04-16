from __future__ import annotations

import json
from typing import Any

from jinja2 import BaseLoader, Environment



def _json_filter(value: Any) -> str:
    """Jinja2 global: serialise any value to a JSON string."""
    from warden.engine.models import Match

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


def build_template_context(matches: list) -> dict[str, Any]:
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


def render_template(value: str, context: dict[str, Any]) -> str:
    """Render a string containing ${{…}} placeholders using Jinja2."""
    if not isinstance(value, str):
        return value
    if "${{" not in value:
        return value
    return _jinja_env.from_string(value).render(context)


def render_value(value: Any, context: dict[str, Any]) -> Any:
    """Recursively render placeholders in strings, dicts, and lists."""
    if isinstance(value, str):
        return render_template(value, context)
    if isinstance(value, dict):
        return {k: render_value(v, context) for k, v in value.items()}
    if isinstance(value, list):
        return [render_value(item, context) for item in value]
    return value
