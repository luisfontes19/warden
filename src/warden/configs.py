import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from warden.managed_policies.base import ManagedPolicyHandler
from warden.managed_policies.linux import LinuxPolicyHandler
from warden.managed_policies.macos import MacOSPolicyHandler


@dataclass(init=True)
class ConfigsData():
    app_data_dir: Path
    rules_dir: Path
    policyHandler: ManagedPolicyHandler
    rules_url: Optional[str]
    interval: int = 10



class Configs:
    configs: ConfigsData

    @staticmethod
    def load_configs() -> ConfigsData:
        import platform

        system = platform.system()
        logging.info(f"Detected platform: {system}")

        if system == "Darwin":

            app_data_dir=Path("Library/Application Support/warden")

            configs = ConfigsData(
                app_data_dir=app_data_dir,
                rules_dir= app_data_dir / "policy-rules",
                interval=10,
                rules_url=None,
                policyHandler=MacOSPolicyHandler()
            )
        elif system == "Linux":
            app_data_dir = Path.home() / ".local" / "share" / "warden"

            configs = ConfigsData(
                app_data_dir=app_data_dir,
                rules_dir=app_data_dir / "policy-rules",
                interval=10,
                rules_url=None,
                policyHandler=LinuxPolicyHandler(),
            )
        else:
            raise NotImplementedError(f"No managed policy handler implemented for platform: {system}")

        Configs.configs = configs
        Configs.configs.policyHandler.init()

        return configs
