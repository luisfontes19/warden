from __future__ import annotations

import base64
import io
import logging
import zipfile
from abc import ABC, abstractmethod
from asyncio.log import logger
from pathlib import Path

import requests


class ManagedPolicyHandler(ABC):
    """Abstract interface for reading MDM-managed policy settings."""

    def __init__(self) -> None:
        self.is_managed: bool|bool = False
        self.rules_url: str | None = None
        self.inline_rules: list[str] | None = None
        self.allow_code_rules: bool | None = None
        self.thread_timeout: int | None = None
        self.refresh_interval: int | None = None
        self.bundle_signing_public_key: str | None = None
        self.bundle_error_url: str | None = None

    @abstractmethod
    def init(self) -> None:
        """Initialize the policy handler, loading any existing policies."""
        pass

    def _validate_bundle_config(self) -> None:
        """Raise if bundle signing is partially configured."""
        if self.rules_url and not self.bundle_signing_public_key:
            raise ValueError(
                "MDM policy sets 'rules-url' but 'bundle-signing-public-key' is missing. "
                "All remotely-delivered rule bundles must be signed."
            )

    @staticmethod
    def get_policy_handler() -> ManagedPolicyHandler:
        from warden.configs import Configs
        return Configs.instance.policyHandler


    def _extract_inline_rules(self, inline_rules_content: list[str]|None = None) -> None:
        if not self.inline_rules: return


        from warden.configs import Configs
        policy_rules_dir = Configs.instance.rules_dir

        policy_rules_dir.mkdir(parents=True, exist_ok=True)

        # Remove previously extracted rules before writing fresh ones
        for existing in policy_rules_dir.glob("*.yml"):
            existing.unlink()

        written = 0
        for idx, encoded in enumerate(self.inline_rules):
            try:
                content = base64.b64decode(encoded).decode("utf-8")
                rule_file = policy_rules_dir / f"rule_{idx:04d}.yml"
                rule_file.write_text(content, encoding="utf-8")
                written += 1
            except Exception as exc:
                logger.warning("Failed to decode inline rule at index %d: %s", idx, exc)

        logger.info(f"Extracted {written} inline rule(s) to {policy_rules_dir}")


    def _download_rules(self, url: str) -> Path | None:
        from warden.configs import Configs
        logging.info(f"Downloading rules from {url}")

        rules_dir = Configs.instance.rules_dir
        rules_dir.mkdir(parents=True, exist_ok=True)

        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            zip_data = response.content
        except Exception as exc:
            logger.error("Failed to download rules from %s: %s", url, exc)
            return None


        for existing in rules_dir.glob("*"):
            existing.unlink()

        try:
            with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
                count = 0
                for name in zf.namelist():
                    # Prevent path traversal
                    target = (rules_dir / name).resolve()

                    if not str(target).startswith(str(rules_dir.resolve())):
                        logger.warning("Skipping unsafe zip entry: %s", name)
                        continue

                    zf.extract(name, rules_dir)
                    count += 1

                logger.info(f"Extracted {count} file(s) from downloaded bundle to {rules_dir}")
        except zipfile.BadZipFile as exc:
            logger.error("Downloaded file is not a valid zip archive: %s", exc)
            return None

        return rules_dir
