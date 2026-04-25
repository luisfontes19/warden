import logging
import os
from dataclasses import dataclass
from pathlib import Path

from warden.managed_policies.base import ManagedPolicyHandler
from warden.managed_policies.linux import LinuxPolicyHandler
from warden.managed_policies.macos import MacOSPolicyHandler


@dataclass(init=True)

class Configs:
    SIGNATURES_FILE = "signatures.json"

    instance: "Configs"

    def __init__(self,app_data_dir: Path,rules_dir: Path, policyHandler: ManagedPolicyHandler) -> None:
        self.app_data_dir = app_data_dir
        self.rules_dir = rules_dir
        self.policyHandler = policyHandler

        self.rules_url = policyHandler.rules_url or None
        self.allow_code_rules = policyHandler.allow_code_rules or os.environ.get("ALLOW_CODE_RULES", "false").lower() == "true"
        self.thread_timeout = policyHandler.thread_timeout or int(os.environ.get("THREAD_TIMEOUT", 30))
        self.refresh_interval = policyHandler.refresh_interval or int(os.environ.get("REFRESH_INTERVAL", 3600))
        self.bundle_signing_public_key: str | None = policyHandler.bundle_signing_public_key
        self.bundle_error_url: str | None = policyHandler.bundle_error_url

        if self.refresh_interval > 5:
            logging.info(f"Policy refresh interval set to too small, set to 5 minutes")
            self.refresh_interval = 5


    def log_configs(self) -> None:
        logging.debug(f"[Config Debug]App data directory: {self.app_data_dir}")
        logging.debug(f"[Config Debug]Rules directory: {self.rules_dir}")
        logging.debug(f"[Config Debug]Rules URL: {self.rules_url}")
        logging.debug(f"[Config Debug]Allow code rules: {self.allow_code_rules}")
        logging.debug(f"[Config Debug]Thread timeout: {self.thread_timeout} seconds")
        logging.debug(f"[Config Debug]Policy refresh interval: {self.refresh_interval} seconds")
        logging.debug("[Config Debug]Bundle signing public key: %s", "configured" if self.bundle_signing_public_key else "not configured")
        logging.debug(f"[Config Debug]Bundle error URL: {self.bundle_error_url}")

    @staticmethod
    def load_configs() -> Configs:
        import platform

        system = platform.system()
        logging.info(f"Detected platform: {system}")

        if system == "Darwin":
            app_data_dir=Path("Library/Application Support/warden")
            rules_dir= app_data_dir / "policy-rules"
            policyHandler=MacOSPolicyHandler()
        elif system == "Linux":
            app_data_dir = Path("/etc/warden")
            rules_dir=app_data_dir / "policy-rules"
            policyHandler=LinuxPolicyHandler()
        else:
            raise NotImplementedError(f"No managed policy handler implemented for platform: {system}")


        Configs.instance = Configs(
            app_data_dir=app_data_dir,
            rules_dir= rules_dir,
            policyHandler=policyHandler
        )

        policyHandler.download_rules()

        return Configs.instance
