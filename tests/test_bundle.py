"""Unit tests for warden.bundle — key generation, signing, and verification."""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from warden.bundle import (DEFAULT_KEY_PATH, create_bundle,
                           create_signatures_data, generate_keypair,
                           load_private_key, public_key_from_b64,
                           public_key_to_b64, save_private_key,
                           write_signatures)
from warden.engine.verifier import (SIGNATURES_FILE, load_signatures,
                                    post_bundle_error, verify_file,
                                    verify_files_checksum)

# ---------------------------------------------------------------------------
# Key generation
# ---------------------------------------------------------------------------


class TestKeygen:
    def test_returns_private_key_and_pub_bytes(self):
        priv, pub_raw = generate_keypair()
        assert isinstance(priv, Ed25519PrivateKey)
        assert isinstance(pub_raw, bytes)
        assert len(pub_raw) == 32  # Ed25519 raw public key is always 32 bytes

    def test_different_calls_produce_different_keys(self):
        _, pub1 = generate_keypair()
        _, pub2 = generate_keypair()
        assert pub1 != pub2

    def test_public_key_roundtrip_b64(self):
        _, pub_raw = generate_keypair()
        b64 = public_key_to_b64(pub_raw)
        recovered = public_key_from_b64(b64)
        from cryptography.hazmat.primitives import serialization
        recovered_raw = recovered.public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        assert recovered_raw == pub_raw

    def test_default_key_path_extension(self):
        assert DEFAULT_KEY_PATH.suffix == ".ed25519"

    def test_save_and_load_private_key(self, tmp_path: Path):
        key_path = tmp_path / "key.ed25519"
        priv, _ = generate_keypair()
        save_private_key(priv, key_path)

        assert key_path.exists()
        assert oct(key_path.stat().st_mode)[-3:] == "600"

        loaded = load_private_key(key_path)
        assert isinstance(loaded, Ed25519PrivateKey)

    def test_save_creates_parent_dirs(self, tmp_path: Path):
        key_path = tmp_path / "nested" / "dir" / "key.ed25519"
        priv, _ = generate_keypair()
        save_private_key(priv, key_path)
        assert key_path.exists()

    def test_load_wrong_key_type_raises(self, tmp_path: Path):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.x25519 import \
            X25519PrivateKey

        x_key = X25519PrivateKey.generate()
        key_path = tmp_path / "wrong.key"
        key_path.write_bytes(
            x_key.private_bytes(
                serialization.Encoding.DER,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        with pytest.raises(TypeError, match="Expected Ed25519"):
            load_private_key(key_path)


# ---------------------------------------------------------------------------
# Per-file verification
# ---------------------------------------------------------------------------


class TestVerifyFile:
    def test_valid_signature_returns_true(self, tmp_path: Path):
        priv, pub_raw = generate_keypair()
        pub = public_key_from_b64(public_key_to_b64(pub_raw))

        target = tmp_path / "file.yml"
        target.write_text("hello: world", encoding="utf-8")
        sig_data = create_signatures_data(tmp_path, priv)

        assert verify_file(target, sig_data["files"]["file.yml"], pub) is True

    def test_tampered_content_returns_false(self, tmp_path: Path):
        priv, pub_raw = generate_keypair()
        pub = public_key_from_b64(public_key_to_b64(pub_raw))

        target = tmp_path / "file.yml"
        target.write_text("hello: world", encoding="utf-8")
        sig_data = create_signatures_data(tmp_path, priv)

        target.write_text("hello: evil", encoding="utf-8")
        assert verify_file(target, sig_data["files"]["file.yml"], pub) is False

    def test_wrong_key_returns_false(self, tmp_path: Path):
        priv1, _ = generate_keypair()
        _, pub2_raw = generate_keypair()
        pub2 = public_key_from_b64(public_key_to_b64(pub2_raw))

        target = tmp_path / "file.yml"
        target.write_text("data", encoding="utf-8")
        sig_data = create_signatures_data(tmp_path, priv1)

        assert verify_file(target, sig_data["files"]["file.yml"], pub2) is False

    def test_invalid_base64_returns_false(self, tmp_path: Path):
        _, pub_raw = generate_keypair()
        pub = public_key_from_b64(public_key_to_b64(pub_raw))
        target = tmp_path / "file.yml"
        target.write_text("x", encoding="utf-8")
        assert verify_file(target, "!!!not-valid-base64!!!", pub) is False


# ---------------------------------------------------------------------------
# signatures.json creation, loading, and checksum
# ---------------------------------------------------------------------------


class TestVerifyFilesChecksum:
    def test_valid_checksum_returns_true(self, tmp_path: Path):
        priv, pub_raw = generate_keypair()
        pub = public_key_from_b64(public_key_to_b64(pub_raw))
        (tmp_path / "rule.yml").write_text("rule")
        data = create_signatures_data(tmp_path, priv)
        assert verify_files_checksum(data, pub) is True

    def test_missing_checksum_returns_false(self, tmp_path: Path):
        _, pub_raw = generate_keypair()
        pub = public_key_from_b64(public_key_to_b64(pub_raw))
        data = {"version": 1, "algorithm": "ed25519", "files": {}}
        assert verify_files_checksum(data, pub) is False

    def test_tampered_files_dict_returns_false(self, tmp_path: Path):
        priv, pub_raw = generate_keypair()
        pub = public_key_from_b64(public_key_to_b64(pub_raw))
        (tmp_path / "rule.yml").write_text("rule")
        data = create_signatures_data(tmp_path, priv)
        # Remove an entry from files after signing — checksum must fail
        data["files"].pop("rule.yml")
        assert verify_files_checksum(data, pub) is False

    def test_wrong_key_returns_false(self, tmp_path: Path):
        priv, _ = generate_keypair()
        _, wrong_pub_raw = generate_keypair()
        wrong_pub = public_key_from_b64(public_key_to_b64(wrong_pub_raw))
        (tmp_path / "rule.yml").write_text("rule")
        data = create_signatures_data(tmp_path, priv)
        assert verify_files_checksum(data, wrong_pub) is False


class TestSignaturesFile:
    def test_create_covers_all_files_recursively(self, tmp_path: Path):
        priv, _ = generate_keypair()
        (tmp_path / "a.yml").write_text("a")
        (tmp_path / "b.yml").write_text("b")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "c.py").write_text("c")

        data = create_signatures_data(tmp_path, priv)
        assert set(data["files"].keys()) == {"a.yml", "b.yml", "sub/c.py"}

    def test_create_excludes_signatures_json(self, tmp_path: Path):
        priv, _ = generate_keypair()
        (tmp_path / "rule.yml").write_text("rule")
        (tmp_path / SIGNATURES_FILE).write_text("old")

        data = create_signatures_data(tmp_path, priv)
        assert SIGNATURES_FILE not in data["files"]

    def test_algorithm_field_is_ed25519(self, tmp_path: Path):
        priv, _ = generate_keypair()
        (tmp_path / "r.yml").write_text("r")
        data = create_signatures_data(tmp_path, priv)
        assert data["algorithm"] == "ed25519"
        assert data["version"] == 1

    def test_write_and_load_roundtrip(self, tmp_path: Path):
        priv, _ = generate_keypair()
        (tmp_path / "x.yml").write_text("x")
        data = create_signatures_data(tmp_path, priv)
        write_signatures(tmp_path, data)

        loaded = load_signatures(tmp_path)
        assert loaded == data

    def test_load_missing_returns_none(self, tmp_path: Path):
        assert load_signatures(tmp_path) is None

    def test_load_malformed_json_returns_none(self, tmp_path: Path):
        (tmp_path / SIGNATURES_FILE).write_text("{broken json{{")
        assert load_signatures(tmp_path) is None


# ---------------------------------------------------------------------------
# create_bundle (high-level)
# ---------------------------------------------------------------------------


class TestSignBundle:
    def test_creates_zip_and_signatures_txt(self, tmp_path: Path):
        key_path = tmp_path / "key.ed25519"
        priv, _ = generate_keypair()
        save_private_key(priv, key_path)

        folder = tmp_path / "rules"
        folder.mkdir()
        (folder / "rule.yml").write_text("version: 1\nrules: []")

        out = tmp_path / "bundle.zip"
        create_bundle(folder, key_path, out)

        assert out.exists()
        assert (folder / SIGNATURES_FILE).exists()

    def test_zip_contains_rules_and_signatures(self, tmp_path: Path):
        key_path = tmp_path / "key.ed25519"
        priv, _ = generate_keypair()
        save_private_key(priv, key_path)

        folder = tmp_path / "rules"
        folder.mkdir()
        (folder / "rule.yml").write_text("version: 1\nrules: []")
        (folder / "handler.py").write_text("def handler(f): pass")

        out = tmp_path / "bundle.zip"
        create_bundle(folder, key_path, out)

        with zipfile.ZipFile(out) as zf:
            names = set(zf.namelist())

        assert "rule.yml" in names
        assert "handler.py" in names
        assert SIGNATURES_FILE in names

    def test_signatures_verify_after_bundle(self, tmp_path: Path):
        priv, pub_raw = generate_keypair()
        key_path = tmp_path / "key.ed25519"
        save_private_key(priv, key_path)

        folder = tmp_path / "rules"
        folder.mkdir()
        rule_file = folder / "rule.yml"
        rule_file.write_text("version: 1\nrules: []")

        create_bundle(folder, key_path, tmp_path / "out.zip")

        pub = public_key_from_b64(public_key_to_b64(pub_raw))
        sig_data = load_signatures(folder)
        assert sig_data is not None
        assert verify_file(rule_file, sig_data["files"]["rule.yml"], pub) is True

    def test_missing_key_file_raises(self, tmp_path: Path):
        folder = tmp_path / "rules"
        folder.mkdir()
        (folder / "r.yml").write_text("v: 1")
        with pytest.raises(Exception):
            create_bundle(folder, tmp_path / "nonexistent.ed25519", tmp_path / "out.zip")

    def test_multiple_files_all_signed(self, tmp_path: Path):
        priv, pub_raw = generate_keypair()
        key_path = tmp_path / "key.ed25519"
        save_private_key(priv, key_path)

        folder = tmp_path / "rules"
        folder.mkdir()
        for i in range(5):
            (folder / f"rule_{i}.yml").write_text(f"version: 1\nrules: []  # {i}")

        create_bundle(folder, key_path, tmp_path / "out.zip")

        pub = public_key_from_b64(public_key_to_b64(pub_raw))
        sig_data = load_signatures(folder)
        assert len(sig_data["files"]) == 5
        for name, sig_b64 in sig_data["files"].items():
            assert verify_file(folder / name, sig_b64, pub) is True


# ---------------------------------------------------------------------------
# post_bundle_error
# ---------------------------------------------------------------------------


class TestPostBundleError:
    def test_does_not_raise_on_connection_refused(self):
        # Port 1 will be refused; the function must swallow the exception
        post_bundle_error("http://127.0.0.1:1", "test error")

    def test_does_not_raise_on_bad_url(self):
        post_bundle_error("http://this-host-does-not-exist.invalid/", "test")
