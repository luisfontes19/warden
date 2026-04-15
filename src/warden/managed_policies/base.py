from __future__ import annotations

from abc import ABC, abstractmethod

from asyncio.log import logger
import base64
import io
import requests
import zipfile
from pathlib import Path

class ManagedPolicyHandler(ABC):
    """Abstract interface for reading MDM-managed policy settings."""

    is_managed = False
    interval: int | None = None
    rules_url: str | None = None
    inline_rules: list[str]|None = None
    allow_code_rules: bool = False

    @abstractmethod
    def init(self) -> None:
        """Initialize the policy handler, loading any existing policies."""
        pass

    @staticmethod
    def get_policy_handler() -> ManagedPolicyHandler:
        from warden.configs import Configs
        return Configs.configs.policyHandler


    def _extract_inline_rules(self, inline_rules_content: list[str]|None = None) -> None:
        if not self.inline_rules: return


        from warden.configs import Configs
        policy_rules_dir = Configs.configs.rules_dir

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
        app_data_dir = Configs.configs.app_data_dir

        url_rules_dir = app_data_dir / "url-rules"
        url_rules_dir.mkdir(parents=True, exist_ok=True)

        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            zip_data = response.content
        except Exception as exc:
            logger.error("Failed to download rules from %s: %s", url, exc)
            return None


        for existing in url_rules_dir.glob("*"):
            existing.unlink()

        try:
            with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
                for name in zf.namelist():
                    # Prevent path traversal
                    target = (url_rules_dir / name).resolve()

                    if not str(target).startswith(str(url_rules_dir.resolve())):
                        logger.warning("Skipping unsafe zip entry: %s", name)
                        continue
                    zf.extract(name, url_rules_dir)

        except zipfile.BadZipFile as exc:
            logger.error("Downloaded file is not a valid zip archive: %s", exc)
            return None

        return url_rules_dir
