from __future__ import annotations

import base64
import importlib.util
import logging
from pathlib import Path

import yaml

from warden.configs import Configs, Path
from warden.engine.actions import ActionResult
from warden.engine.file_utils import resolve_file_path
from warden.engine.models import Match, Rule, RuleFile
from warden.engine.verifier import (load_signatures, post_bundle_error,
                                    public_key_from_b64, verify_bundle,
                                    verify_file)


def invoke_code_handler(
    code_path: str,
    rules_dir: Path,
    filename: str,
    bundle_signing_public_key: str | None = None,
) -> None:
    """Dynamically load a Python file and call its handler(filename) function."""
    if not Configs.instance.allow_code_rules:
        return logging.warning(
            "Code execution is disabled by config, skipping code handler: %s", code_path
        )

    rules_dir_resolved = rules_dir.resolve()
    resolved = (rules_dir / code_path).resolve()

    if not str(resolved).startswith(str(rules_dir_resolved) + "/") and resolved != rules_dir_resolved:
        raise ValueError(f"Path traversal detected in code path: {code_path!r}")

    if not resolved.exists():
        raise FileNotFoundError(f"Code handler file not found: {resolved}")

    if bundle_signing_public_key is not None:
        sig_data = load_signatures(rules_dir_resolved)
        rel = str(resolved.relative_to(rules_dir_resolved))
        sig_b64 = (sig_data or {}).get("files", {}).get(rel)
        if sig_b64 is None:
            raise ValueError(
                f"Code handler {code_path!r} has no signature in signatures.json"
            )
        try:
            pub_key = public_key_from_b64(bundle_signing_public_key)
        except Exception as exc:
            raise ValueError(f"Invalid bundle public key: {exc}") from exc
        if not verify_file(resolved, sig_b64, pub_key):
            raise ValueError(f"Code handler {code_path!r} has an invalid signature")

    logging.info("Invoking code handler %s for %s", resolved, filename)

    spec = importlib.util.spec_from_file_location("_warden_rule_handler", resolved)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {resolved}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]

    if not hasattr(module, "handler"):
        raise AttributeError(f"Code handler {resolved} must define a 'handler(filename)' function")

    module.handler(filename)


class RuleEngine:
    """Loads rules and evaluates / enforces them against files."""

    def __init__(
        self,
        folder: str | None = None,
        rule_files: list[str] | None = None,
        bundle_signing_public_key: str | None = None,
    ) -> None:
        self.folder = folder
        self.rule_files = rule_files
        self._bundle_signing_public_key = bundle_signing_public_key
        self.rules: list[Rule] = []
        self._load_all()

    def _load_all(self) -> None:
        self.rules = []
        self.rules.extend(self._load_rules_from_folder(Configs.instance.rules_dir))
        self.rules.extend(self._load_inline_rules())
        if self.folder:
            self.rules.extend(self._load_rules_from_folder(self.folder))

        for f in (self.rule_files or []):
            self.rules.extend(self._load_rules_from_file(f))
        logging.info("Loaded %d rule(s)", len(self.rules))

        for rule in self.rules:
            rule.apply_defaults()

    def reload(self) -> None:
        """Re-read all rule sources and rebuild the rules list."""
        logging.info("Reloading rules")
        self._load_all()

    def _get_bundle_error_url(self) -> str | None:
        try:
            return Configs.instance.bundle_error_url
        except AttributeError:
            return None

    @staticmethod
    def _load_rules_from_file(path: str | Path) -> list[Rule]:
        try:
            return RuleFile(path).rules
        except Exception as exc:
            logging.error("Error loading %s: %s", path, exc)
            return []

    def _load_rules_from_folder(self, folder: str | Path) -> list[Rule]:
        folder_path = Path(folder)
        if not folder_path.exists():
            return []

        public_key = Configs.instance.bundle_signing_public_key

        if public_key is None:
            rules: list[Rule] = []
            for yml in folder_path.glob("*.yml"):
                rules.extend(self._load_rules_from_file(yml))
            return rules

        # With a signing key: verify the manifest checksum first, then each file.
        verified = verify_bundle(folder_path, public_key, self._get_bundle_error_url())
        if verified is None:
            return []

        rules = []
        for yml in sorted(folder_path.glob("*.yml")):
            if yml.resolve() not in verified:
                msg = f"Unverified rule file skipped: {yml.name}"
                logging.warning(msg)
                if url := self._get_bundle_error_url():
                    post_bundle_error(url, msg)
                continue
            loaded = self._load_rules_from_file(yml)
            for rule in loaded:
                rule.bundle_signing_public_key = public_key
            rules.extend(loaded)
        return rules

    @staticmethod
    def _load_inline_rules() -> list[Rule]:
        handler = Configs.instance.policyHandler
        if not handler.inline_rules:
            return []

        rules: list[Rule] = []
        for idx, encoded in enumerate(handler.inline_rules):
            try:
                content = base64.b64decode(encoded).decode("utf-8")
                data = yaml.safe_load(content)
                if not data or "rules" not in data:
                    continue
                for r in data["rules"]:
                    rules.append(Rule.from_dict(r))
            except Exception as exc:
                logging.error("Error loading inline rule %d: %s", idx, exc)

        logging.info("Loaded %d inline rule(s) from managed policy", len(rules))
        return rules

    def _rules_for_file(self, file: str) -> list[Rule]:
        resolved = resolve_file_path(file)
        return [rule for rule in self.rules if resolved in rule.files]

    def run(self) -> list[Match]:
        """Evaluate every rule and return all matches."""
        return [m for rule in self.rules for m in rule.evaluate()]

    def evaluate_file(self, file: str) -> list[Match]:
        """Evaluate only rules that target the specified file."""
        return [
            m
            for rule in self._rules_for_file(file)
            for m in rule.evaluate_against_file(file)
        ]

    def enforce(self, file: str) -> list[Match]:
        """Evaluate rules targeting file, apply actions, and write changes to disk."""
        results: list[Match] = []
        for rule in self._rules_for_file(file):
            matches = rule.evaluate_against_file(file)
            if not matches:
                logging.debug("Rule %r: no match for %s", rule.rule_id, file)
                continue

            logging.info("Rule %r: %d match(es) on %s", rule.rule_id, len(matches), file)

            result = rule.apply_actions(matches)
            if isinstance(result, ActionResult):
                if result is ActionResult.FILE_DELETED:
                    logging.info("Rule %r: deleting %s", rule.rule_id, file)
                    Path(matches[0].file).unlink(missing_ok=True)
                else:
                    logging.info("Rule %r: action result %s", rule.rule_id, result.value)
            elif result is not None:
                logging.info("Rule %r: writing updated content to %s", rule.rule_id, file)
                Path(matches[0].file).write_text(result, encoding="utf-8")

            results.extend(matches)
        return results

    def restore_defaults(self, file: str) -> None:
        """For each rule targeting file that has a default, restore the file content."""
        for rule in self._rules_for_file(file):
            rule.apply_defaults()

    def monitoring_files(self) -> list[str]:
        """Return a list of all files that are targeted by rules."""
        return list({f for rule in self.rules for f in rule.files})
