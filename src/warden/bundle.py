"""Bundle signing for Warden rule packages — CLI use only.

Responsibility: create signed bundles (keygen, sign files, write signatures.json, zip).
Verification of bundles at rule-load time lives in warden.engine.verifier.

Uses Ed25519 (EdDSA) from the `cryptography` library for signing.

Key hierarchy:
  key.ed25519   (Ed25519 private key — admin keeps this secret)
      └─ sign(file_bytes) ─► per-file signature stored in signatures.json

  public key    (derived from key.ed25519)
      └─ distributed via MDM as bundle-signing-public-key (base64 raw bytes)
      └─ used by agents to verify signatures without being able to forge them

NOTE: Replace Ed25519 with ML-DSA-65 once the cryptography library's bundled
OpenSSL has the post-quantum provider enabled (cryptography >= 44 + OpenSSL 3.5+).
"""

from __future__ import annotations

import base64
import json
import logging
import zipfile
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey)

from warden.configs import Configs

DEFAULT_KEY_PATH = Path.home() / ".warden" / "key.ed25519"


# ---------------------------------------------------------------------------
# Key generation and serialisation
# ---------------------------------------------------------------------------


def generate_keypair() -> tuple[Ed25519PrivateKey, bytes]:
    """Generate an Ed25519 key pair.

    Returns ``(private_key, public_key_raw_bytes)``.

    - Save *private_key* to disk with :func:`save_private_key`.
    - Pass ``base64(public_key_raw_bytes)`` to MDM as ``bundle-signing-public-key``.
    """
    private_key = Ed25519PrivateKey.generate()
    pub_raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return private_key, pub_raw


def save_private_key(private_key: Ed25519PrivateKey, path: Path) -> None:
    """Write the private key to *path* in DER/PKCS8 format (mode 0o600)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    path.chmod(0o600)


def load_private_key(path: Path) -> Ed25519PrivateKey:
    """Load an Ed25519 private key from a DER/PKCS8 file."""
    key = serialization.load_der_private_key(path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise TypeError(f"Expected Ed25519 private key, got {type(key).__name__}")
    return key


def save_public_key(pub_raw: bytes, path: Path) -> None:
    """Write the base64-encoded public key to *path*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(public_key_to_b64(pub_raw) + "\n", encoding="ascii")


def public_key_to_b64(pub_raw: bytes) -> str:
    """Base64-encode a public key for MDM config."""
    return base64.b64encode(pub_raw).decode("ascii")


def public_key_from_b64(b64: str) -> Ed25519PublicKey:
    """Decode an Ed25519 public key from the base64 MDM config value."""
    return Ed25519PublicKey.from_public_bytes(base64.b64decode(b64))


# ---------------------------------------------------------------------------
# Per-file signing
# ---------------------------------------------------------------------------


def _sign_file(path: Path, private_key: Ed25519PrivateKey) -> str:
    """Sign file bytes with Ed25519 and return base64-encoded signature."""
    return base64.b64encode(private_key.sign(path.read_bytes())).decode("ascii")


# ---------------------------------------------------------------------------
# signatures.json creation
# ---------------------------------------------------------------------------


def create_signatures_data(
    folder: Path, private_key: Ed25519PrivateKey
) -> dict[str, Any]:
    """Sign every non-dotfile in *folder* (excluding signatures.json) and return the manifest.

    The ``checksum`` field is an Ed25519 signature over the canonical JSON of
    the ``files`` dict. The engine verifies this checksum first to ensure the
    manifest has not been tampered with before checking individual file signatures.
    """
    files: dict[str, str] = {}
    for file_path in sorted(folder.rglob("*")):
        if not file_path.is_file():
            continue
        if file_path.name.startswith("."):
            continue
        if file_path.name == Configs.SIGNATURES_FILE:
            continue
        rel = str(file_path.relative_to(folder))
        files[rel] = _sign_file(file_path, private_key)

    files_bytes = json.dumps(files, sort_keys=True).encode("utf-8")
    checksum = base64.b64encode(private_key.sign(files_bytes)).decode("ascii")
    return {"version": 1, "algorithm": "ed25519", "checksum": checksum, "files": files}


def write_signatures(folder: Path, data: dict[str, Any]) -> Path:
    """Write *data* as JSON to ``signatures.json`` inside *folder*."""
    sig_path = folder / Configs.SIGNATURES_FILE
    sig_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return sig_path


# ---------------------------------------------------------------------------
# High-level bundle creation
# ---------------------------------------------------------------------------


def create_bundle(folder: Path, private_key_path: Path, output_path: Path) -> None:
    """Sign every non-dotfile in *folder* and package the result as a zip at *output_path*.

    Writes ``signatures.json`` into *folder* before zipping.
    Dotfiles (names starting with ``.``) are excluded from both signing and the archive.
    """
    private_key = load_private_key(private_key_path)

    sig_data = create_signatures_data(folder, private_key)
    write_signatures(folder, sig_data)
    logging.info("Signed %d file(s) in %s", len(sig_data["files"]), folder)

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(folder.rglob("*")):
            if not file_path.is_file():
                continue
            if file_path.name.startswith("."):
                continue
            zf.write(file_path, file_path.relative_to(folder))

    logging.info("Bundle written to %s", output_path)
