"""Integration tests for bundle signature verification in the rule engine.

These tests exercise:
- RuleEngine only loading verified rule files when a signing key is configured
- RuleEngine refusing to load from a folder with no signatures.json when a key is set
- RuleEngine skipping individual files that fail verification
- Code handler signature verification in actions.py

All tests use real files and real crypto — no patches needed because
RuleEngine accepts bundle_signing_public_key as a constructor argument,
and Rule accepts it directly for code-handler tests.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from cryptography.hazmat.primitives import serialization

from warden.bundle import (
    create_signatures_data,
    generate_keypair,
    public_key_to_b64,
    write_signatures,
)
from warden.engine.rules_engine import RuleEngine, invoke_code_handler

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_RULE_CONTENT = """\
version: 1
rules:
  - id: test-rule
    file: /tmp/warden_test_target.txt
    patterns:
      - contains: badword
    actions:
      - delete: ~
"""


def _write_rule(folder: Path, name: str = "rules.yml", content: str = _RULE_CONTENT) -> Path:
    path = folder / name
    path.write_text(content, encoding="utf-8")
    return path


def _pub_b64(priv) -> str:
    """Return base64-encoded raw public key for a given Ed25519 private key."""
    raw = priv.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return public_key_to_b64(raw)


def _sign_folder(folder: Path, priv) -> str:
    """Sign all files in folder and return base64 public key."""
    sig_data = create_signatures_data(folder, priv)
    write_signatures(folder, sig_data)
    return _pub_b64(priv)


# ---------------------------------------------------------------------------
# Shared fixture: isolate engine from the real system Configs instance
# ---------------------------------------------------------------------------


def _mock_configs(tmp_path: Path):
    """Return a mock Configs.instance that has no rules_dir rules and no inline rules."""
    mock = MagicMock()
    mock.rules_dir = tmp_path / "_empty_rules_dir"  # does not exist → no rules loaded
    mock.policyHandler.inline_rules = []
    mock.bundle_signing_public_key = None
    mock.bundle_error_url = None
    return mock


# ---------------------------------------------------------------------------
# Loading without a signing key (existing behaviour unchanged)
# ---------------------------------------------------------------------------


class TestNoSigningKey:
    def test_loads_rules_normally_without_key(self, tmp_path: Path):
        folder = tmp_path / "rules"
        folder.mkdir()
        _write_rule(folder)

        with patch("warden.engine.rules_engine.Configs") as mock_cfg:
            mock_cfg.instance = _mock_configs(tmp_path)
            engine = RuleEngine(folder=str(folder))
        assert len(engine.rules) == 1

    def test_ignores_signatures_txt_when_no_key(self, tmp_path: Path):
        """signatures.json present but no key configured → load as normal."""
        folder = tmp_path / "rules"
        folder.mkdir()
        _write_rule(folder)
        priv, _ = generate_keypair()
        _sign_folder(folder, priv)

        with patch("warden.engine.rules_engine.Configs") as mock_cfg:
            mock_cfg.instance = _mock_configs(tmp_path)
            engine = RuleEngine(folder=str(folder))
        assert len(engine.rules) == 1


# ---------------------------------------------------------------------------
# Loading WITH a signing key
# ---------------------------------------------------------------------------


class TestWithSigningKey:
    def test_loads_verified_rules(self, tmp_path: Path):
        folder = tmp_path / "rules"
        folder.mkdir()
        priv, _ = generate_keypair()
        _write_rule(folder)
        pub_b64 = _sign_folder(folder, priv)

        engine = RuleEngine(folder=str(folder), bundle_signing_public_key=pub_b64)
        assert len(engine.rules) == 1

    def test_rejects_folder_without_signatures_txt(self, tmp_path: Path):
        folder = tmp_path / "rules"
        folder.mkdir()
        _write_rule(folder)

        priv, _ = generate_keypair()
        engine = RuleEngine(folder=str(folder), bundle_signing_public_key=_pub_b64(priv))
        assert len(engine.rules) == 0

    def test_rejects_tampered_rule_file(self, tmp_path: Path):
        folder = tmp_path / "rules"
        folder.mkdir()
        priv, _ = generate_keypair()
        rule_file = _write_rule(folder)
        pub_b64 = _sign_folder(folder, priv)

        # Tamper after signing
        rule_file.write_text(_RULE_CONTENT + "\n  # tampered", encoding="utf-8")

        engine = RuleEngine(folder=str(folder), bundle_signing_public_key=pub_b64)
        assert len(engine.rules) == 0

    def test_loads_only_verified_files_when_some_tampered(self, tmp_path: Path):
        folder = tmp_path / "rules"
        folder.mkdir()
        priv, _ = generate_keypair()
        good = _write_rule(folder, "good.yml")
        _write_rule(folder, "bad.yml")
        pub_b64 = _sign_folder(folder, priv)

        # Tamper only bad.yml
        (folder / "bad.yml").write_text("version: 1\nrules: []  # tampered")

        engine = RuleEngine(folder=str(folder), bundle_signing_public_key=pub_b64)
        # good.yml has 1 rule; bad.yml is rejected
        assert len(engine.rules) == 1
        assert engine.rules[0].rule_id == "test-rule"

    def test_wrong_public_key_rejects_all(self, tmp_path: Path):
        folder = tmp_path / "rules"
        folder.mkdir()
        priv, _ = generate_keypair()
        _write_rule(folder)
        _sign_folder(folder, priv)

        # Use a completely different key for verification
        _, wrong_pub_raw = generate_keypair()
        wrong_pub_b64 = public_key_to_b64(wrong_pub_raw)

        engine = RuleEngine(folder=str(folder), bundle_signing_public_key=wrong_pub_b64)
        assert len(engine.rules) == 0

    def test_empty_folder_with_key_loads_nothing(self, tmp_path: Path):
        folder = tmp_path / "rules"
        folder.mkdir()
        priv, _ = generate_keypair()
        pub_b64 = _sign_folder(folder, priv)

        engine = RuleEngine(folder=str(folder), bundle_signing_public_key=pub_b64)
        assert len(engine.rules) == 0

    def test_bundle_signing_key_propagated_to_rules(self, tmp_path: Path):
        folder = tmp_path / "rules"
        folder.mkdir()
        priv, _ = generate_keypair()
        _write_rule(folder)
        pub_b64 = _sign_folder(folder, priv)

        engine = RuleEngine(folder=str(folder), bundle_signing_public_key=pub_b64)
        assert len(engine.rules) == 1
        assert engine.rules[0].bundle_signing_public_key == pub_b64


# ---------------------------------------------------------------------------
# Code handler signature verification
# ---------------------------------------------------------------------------


class TestCodeHandlerSignatureVerification:
    def test_signed_handler_executes(self, tmp_path: Path):
        handler_code = (
            "def handler(filename):\n"
            "    from pathlib import Path\n"
            "    Path(filename).write_text('handled', encoding='utf-8')\n"
        )
        (tmp_path / "handler.py").write_text(handler_code, encoding="utf-8")
        target = tmp_path / "target.txt"
        target.write_text("original", encoding="utf-8")

        priv, _ = generate_keypair()
        sig_data = create_signatures_data(tmp_path, priv)
        write_signatures(tmp_path, sig_data)

        with patch("warden.engine.rules_engine.Configs") as mock_cfg:
            mock_cfg.instance.allow_code_rules = True
            invoke_code_handler(
                "handler.py", tmp_path, str(target),
                bundle_signing_public_key=_pub_b64(priv),
            )

        assert target.read_text() == "handled"

    def test_unsigned_handler_raises(self, tmp_path: Path):
        (tmp_path / "handler.py").write_text("def handler(f): pass", encoding="utf-8")
        target = tmp_path / "target.txt"
        target.write_text("x", encoding="utf-8")

        priv, _ = generate_keypair()

        with patch("warden.engine.rules_engine.Configs") as mock_cfg:
            mock_cfg.instance.allow_code_rules = True
            with pytest.raises(ValueError, match="no signature"):
                invoke_code_handler(
                    "handler.py", tmp_path, str(target),
                    bundle_signing_public_key=_pub_b64(priv),
                )

    def test_tampered_handler_raises(self, tmp_path: Path):
        handler_file = tmp_path / "handler.py"
        handler_file.write_text("def handler(f): pass", encoding="utf-8")
        target = tmp_path / "target.txt"
        target.write_text("x", encoding="utf-8")

        priv, _ = generate_keypair()
        sig_data = create_signatures_data(tmp_path, priv)
        write_signatures(tmp_path, sig_data)

        handler_file.write_text("def handler(f): open('/tmp/evil','w')", encoding="utf-8")

        with patch("warden.engine.rules_engine.Configs") as mock_cfg:
            mock_cfg.instance.allow_code_rules = True
            with pytest.raises(ValueError, match="invalid signature"):
                invoke_code_handler(
                    "handler.py", tmp_path, str(target),
                    bundle_signing_public_key=_pub_b64(priv),
                )

    def test_no_signing_key_skips_signature_check(self, tmp_path: Path):
        (tmp_path / "handler.py").write_text("def handler(f):\n    pass\n", encoding="utf-8")
        target = tmp_path / "target.txt"
        target.write_text("x", encoding="utf-8")

        with patch("warden.engine.rules_engine.Configs") as mock_cfg:
            mock_cfg.instance.allow_code_rules = True
            invoke_code_handler("handler.py", tmp_path, str(target))
