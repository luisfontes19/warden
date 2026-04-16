import logging
import os
from dataclasses import dataclass
from pathlib import Path

from warden.managed_policies.base import ManagedPolicyHandler
from warden.managed_policies.linux import LinuxPolicyHandler
from warden.managed_policies.macos import MacOSPolicyHandler


@dataclass(init=True)

class Configs:
    instance: "Configs"

    def __init__(self,app_data_dir: Path,rules_dir: Path, policyHandler: ManagedPolicyHandler) -> None:
        self.app_data_dir = app_data_dir
        self.rules_dir = rules_dir
        self.policyHandler = policyHandler

        self.rules_url = policyHandler.rules_url or None
        self.allow_code_rules = policyHandler.allow_code_rules or os.environ.get("ALLOW_CODE_RULES", "false").lower() == "true"
        self.thread_timeout = policyHandler.thread_timeout or int(os.environ.get("THREAD_TIMEOUT", 30))
        self.refresh_interval = policyHandler.refresh_interval or int(os.environ.get("REFRESH_INTERVAL", 3600))

        if self.refresh_interval > 5:
            logging.info(f"Policy refresh interval set to too small, set to 5 minutes")
            self.refresh_interval = 5


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
            app_data_dir = Path.home() / ".local" / "share" / "warden"
            rules_dir=app_data_dir / "policy-rules"
            policyHandler=LinuxPolicyHandler()
        else:
            raise NotImplementedError(f"No managed policy handler implemented for platform: {system}")

        policyHandler.init()

        Configs.instance = Configs(
            app_data_dir=app_data_dir,
            rules_dir= rules_dir,
            policyHandler=policyHandler
        )

        return Configs.instance
