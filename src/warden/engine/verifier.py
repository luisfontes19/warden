"""Bundle signature verification for the Warden rule engine.

Responsibility: verify bundles when loading rules.
bundle.py creates bundles; this module verifies them. They are independent.
"""
from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Any

import requests
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

SIGNATURES_FILE = "signatures.json"


def load_signatures(folder: Path) -> dict[str, Any] | None:
    sig_path = folder / SIGNATURES_FILE
    if not sig_path.exists():
        return None
    try:
        return json.loads(sig_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logging.warning("Failed to parse %s in %s: %s", SIGNATURES_FILE, folder, exc)
        return None


def public_key_from_b64(b64: str) -> Ed25519PublicKey:
    return Ed25519PublicKey.from_public_bytes(base64.b64decode(b64))


def verify_file(path: Path, sig_b64: str, public_key: Ed25519PublicKey) -> bool:
    try:
        public_key.verify(base64.b64decode(sig_b64), path.read_bytes())
        return True
    except InvalidSignature:
        return False
    except Exception as exc:
        logging.warning("Signature check failed for %s: %s", path, exc)
        return False


def verify_files_checksum(sig_data: dict[str, Any], public_key: Ed25519PublicKey) -> bool:
    """Verify the Ed25519 signature over the files dict (manifest integrity check)."""
    checksum = sig_data.get("checksum")
    if not checksum:
        return False
    files = sig_data.get("files", {})
    files_bytes = json.dumps(files, sort_keys=True).encode("utf-8")
    try:
        public_key.verify(base64.b64decode(checksum), files_bytes)
        return True
    except (InvalidSignature, Exception):
        return False


def post_bundle_error(url: str, message: str) -> None:
    try:
        resp = requests.post(
            url,
            json={"error": message, "source": "warden-bundle-verification"},
            timeout=10,
        )
        resp.raise_for_status()
        logging.info("Bundle error reported to %s", url)
    except Exception as exc:
        logging.warning("Could not POST bundle error to %s: %s", url, exc)


def _report(url: str | None, message: str) -> None:
    logging.error(message)
    if url:
        post_bundle_error(url, message)


def verify_bundle(
    folder: Path, public_key_b64: str, error_url: str | None = None
) -> frozenset[Path] | None:
    """Verify a bundle folder. Returns verified file paths, or None if the manifest is invalid.

    Verification order:
    1. Load signatures.json — fail fast if missing or unparseable.
    2. Verify the checksum (Ed25519 sig over the files dict) — fail fast if invalid.
       This proves the manifest itself has not been tampered with.
    3. For each file in the manifest: verify it exists on disk and its signature is valid.
       Each failure is reported individually; valid files are collected.
    """
    sig_data = load_signatures(folder)
    if sig_data is None:
        _report(error_url, f"signatures.json missing or unreadable in {folder}")
        return None

    try:
        public_key = public_key_from_b64(public_key_b64)
    except Exception as exc:
        _report(error_url, f"Invalid bundle public key: {exc}")
        return None

    if not verify_files_checksum(sig_data, public_key):
        _report(error_url, f"Bundle manifest checksum invalid for {folder}")


    verified: set[Path] = set()
    for rel_str, sig_b64 in sig_data.get("files", {}).items():
        file_path = (folder / rel_str).resolve()
        if not file_path.exists():
            _report(error_url, f"Bundle file missing on disk: {rel_str}")
            continue
        if not verify_file(file_path, sig_b64, public_key):
            _report(error_url, f"Bundle file signature invalid: {rel_str}")
            continue
        verified.add(file_path)

    return frozenset(verified)
