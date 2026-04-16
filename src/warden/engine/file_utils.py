from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any
import logging


def resolve_file_path(raw: str) -> str:
    """Expand ~ to the real user's home and resolve to an absolute path."""
    if raw.startswith("~/"):
        raw = os.getlogin() + raw[1:]
    return str(Path(raw).resolve())


def resolve_filetype(path: Path, filetype: str | None) -> str:
    return filetype or path.suffix.lstrip(".").lower() or "text"


def load_file(path: Path, filetype: str | None) -> Any:
    resolved = resolve_filetype(path, filetype)
    logging.debug("Loading %s as %s", path, resolved)
    return parse_content(path.read_bytes(), resolved)


def parse_content(raw: bytes | str, filetype: str) -> Any:
    if filetype == "json":
        return json.loads(raw)
    if filetype == "binary":
        return raw if isinstance(raw, bytes) else raw.encode()
    return raw if isinstance(raw, str) else raw.decode("utf-8")
