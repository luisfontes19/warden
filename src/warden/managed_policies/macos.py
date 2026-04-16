from __future__ import annotations

import logging
import plistlib
from pathlib import Path

from warden.managed_policies.base import ManagedPolicyHandler

PLIST_PATH = Path("/Library/Managed Preferences/com.thesecurityvault.warden.plist")

class MacOSPolicyHandler(ManagedPolicyHandler):
    """Reads MDM-managed preferences from the macOS managed preferences plist."""

    def init(self) -> None:
        logging.info("Initializing MacOSPolicyHandler")
        self.parse()

        if self.has_policy:
            self._extract_inline_rules()
            self._download_rules(self.rules_url) if self.rules_url else None


    def parse(self):
        if not PLIST_PATH.exists():
            logging.info("Managed preferences plist not found at %s", PLIST_PATH)
            return

        self.has_policy = True

        try:
            with PLIST_PATH.open("rb") as f:
                content = plistlib.load(f)
                self.rules_url = content.get("rules-url")
                self.inline_rules = content.get("rules")
                self.allow_code_rules = bool(content.get("allow-code-rules") if content.get("allow-code-rules") is not None else False)
                self.thread_timeout = int(content.get("thread-timeout", self.thread_timeout))
                self.refresh_interval = int(content.get("refresh-interval", None))

                logging.debug(f"Parsed managed preferences: refresh_interval={self.refresh_interval}, rules_url={self.rules_url}, inline_rules={'present' if self.inline_rules else 'none'}")
        except Exception as exc:
            logging.warning("Failed to load managed preferences: %s", exc)

