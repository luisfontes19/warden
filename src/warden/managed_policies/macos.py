from __future__ import annotations

import logging
import plistlib
from pathlib import Path

from warden.managed_policies.base import ManagedPolicyHandler

PLIST_PATH = Path("/Library/Managed Preferences/com.thesecurityvault.warden.plist")

class MacOSPolicyHandler(ManagedPolicyHandler):
    """Reads MDM-managed preferences from the macOS managed preferences plist."""

    def parse(self):
        if not PLIST_PATH.exists():
            logging.info("Managed preferences plist not found at %s", PLIST_PATH)
            return

        self.has_policy = True

        try:
            with PLIST_PATH.open("rb") as f:
                content = plistlib.load(f)
                self.rules_url = content.get("rules-url")
                self.rules_url_headers = content.get("rules-url-headers")
                self.inline_rules = content.get("rules")
                self.allow_code_rules = bool(content.get("allow-code-rules") if content.get("allow-code-rules") is not None else False)
                self.thread_timeout = int(content.get("thread-timeout", self.thread_timeout))
                self.refresh_interval = int(content.get("refresh-interval", None))
                self.bundle_signing_public_key = content.get("bundle-signing-public-key")
                self.bundle_error_url = content.get("bundle-error-url")
                self._validate_bundle_config()

                logging.debug(
                    "Parsed managed preferences: refresh_interval=%s, rules_url=%s, "
                    "inline_rules=%s, bundle_signing=%s",
                    self.refresh_interval,
                    self.rules_url,
                    "present" if self.inline_rules else "none",
                    "configured" if self.bundle_signing_public_key else "none",
                )
        except Exception as exc:
            logging.warning("Failed to load managed preferences: %s", exc)

