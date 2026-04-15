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
                self.interval = int(content.get("interval", "0"))
                self.rules_url = content.get("rules-url")
                self.inline_rules = content.get("rules")
                self.allow_code_rules = bool(content.get("allow-code-rules", False))

                logging.debug(f"Parsed managed preferences: interval={self.interval}, rules_url={self.rules_url}, inline_rules={'present' if self.inline_rules else 'none'}")
        except Exception as exc:
            logging.warning("Failed to load managed preferences: %s", exc)

