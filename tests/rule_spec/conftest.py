"""Shared helpers for rule_spec tests."""
from __future__ import annotations

import json
import tempfile


def tmp_text(content: str, suffix: str = ".txt") -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False, encoding="utf-8")
    f.write(content)
    f.close()
    return f.name


def tmp_json(data: object, suffix: str = ".json") -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False, encoding="utf-8")
    json.dump(data, f)
    f.close()
    return f.name


def tmp_binary(data: bytes, suffix: str = ".bin") -> str:
    f = tempfile.NamedTemporaryFile(mode="wb", suffix=suffix, delete=False)
    f.write(data)
    f.close()
    return f.name
