from __future__ import annotations

import json
import logging
from pathlib import Path

from warden.managed_policies.base import ManagedPolicyHandler

logger = logging.getLogger(__name__)

POLICY_PATH = Path("/etc/warden/policy.json")
APP_SUPPORT_DIR = Path("/var/lib/warden")
POLICY_RULE_DIR = APP_SUPPORT_DIR / "policy-rules"


class LinuxPolicyHandler(ManagedPolicyHandler):
    """Reads managed policy settings from /etc/warden/policy.json."""

    has_policy: bool = False

    def init(self) -> None:
        logging.info("Initializing LinuxPolicyHandler")
        self.parse()

        if self.has_policy and self.rules_url:
            self._download_rules(self.rules_url)

    def parse(self) -> None:
        if not POLICY_PATH.exists():
            logger.info("Managed policy file not found at %s", POLICY_PATH)
            return

        self.has_policy = True

        try:
            content = json.loads(POLICY_PATH.read_bytes())
            self.rules_url = content.get("rules-url")
            self.inline_rules = content.get("rules")
            self.allow_code_rules = bool(content.get("allow-code-rules") if content.get("allow-code-rules") is not None else False)
            self.thread_timeout = int(content.get("thread-timeout", self.thread_timeout))
            self.refresh_interval = int(content.get("refresh-interval", None))

            logger.debug(
                "Parsed managed policy: refresh_interval=%s, rules_url=%s, inline_rules=%s, allow_code_rules=%s",
                self.refresh_interval,
                self.rules_url,
                "present" if self.inline_rules else "none",
            )
        except Exception as exc:
            logger.warning("Failed to load managed policy: %s", exc)

    def get_policy_rules_dir(self) -> Path:
        return POLICY_RULE_DIR

    def get_app_support_dir(self) -> Path:
        return APP_SUPPORT_DIR
