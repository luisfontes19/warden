from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def resolve_file_path(raw: str) -> str:
    """Expand ~ to the real user's home and resolve to an absolute path."""
    if raw.startswith("~/"):
        raw = os.getlogin() + raw[1:]
    return str(Path(raw).resolve())


def resolve_filetype(path: Path, filetype: str | None) -> str:
    return filetype or path.suffix.lstrip(".").lower() or "text"


def load_file(path: Path, filetype: str | None) -> Any:
    resolved = resolve_filetype(path, filetype)
    if resolved == "json":
        return json.loads(path.read_bytes())
    if resolved == "binary":
        return path.read_bytes()
    return path.read_text(encoding="utf-8")
