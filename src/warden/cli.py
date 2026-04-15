

import argparse
import asyncio
import json
import logging
import os

from warden.configs import Configs
from warden.rules_engine import RuleEngine

class Cli:

    def __init__(self,
                 rule_files: list[str] | None = None
        ) -> None:

        self.rule_engine = RuleEngine(rule_files=rule_files)

    async def handle_changes(self, file_changed: str) -> None:
        logging.info(f"{file_changed} changed", )
        self.rule_engine.enforce(file_changed)


    async def loop(self) -> None:
        files: list[str] = self.rule_engine.monitoring_files()
        logging.info("Monitoring files: %s", json.dumps(files))

        mod_time: dict[str, float] = {}

        while True:

            for path in files:
                try:
                    mtime = os.path.getmtime(path)
                except FileNotFoundError:
                    mtime = 0.0

                if mtime != mod_time.get(path, 0.0):
                    mod_time[path] = mtime
                    await self.handle_changes(path)

            await asyncio.sleep(Configs.configs.interval)


def main() -> None:
    parser = argparse.ArgumentParser(description="Warden - file rule enforcement")
    parser.add_argument(
        "-r",
        dest="rule_files",
        action="append",
        metavar="RULE_FILE",
        default=[],
        help="Path to a rules file (can be specified multiple times)",
    )
    args = parser.parse_args()

    Configs.load_configs()
    cli = Cli(rule_files=args.rule_files or None)
    asyncio.run(cli.loop())


if __name__ == "__main__":
    main()
