

import argparse
import json
import logging
import os

from warden.engine.rules_engine import RuleEngine
from watchdog.events import FileSystemEvent, RegexMatchingEventHandler
from watchdog.observers import Observer

from warden.configs import Configs

class _RuleHandler(RegexMatchingEventHandler):
    """Watchdog handler that enforces rules when a monitored file changes."""

    def __init__(self, rule_engine: RuleEngine, regexes: list[str]) -> None:
        super().__init__(regexes=regexes)
        self.rule_engine = rule_engine

    def on_modified(self, event: FileSystemEvent) -> None:
        path = os.path.realpath(event.src_path)
        logging.info("%s changed", path)
        self.rule_engine.enforce(str(path))

    on_created = on_modified


class Cli:

    def __init__(self, rule_files: list[str] | None = None) -> None:
        self.rule_engine = RuleEngine(rule_files=rule_files)

    def loop(self) -> None:
        files = self.rule_engine.monitoring_files()
        logging.info("Monitoring files: %s", json.dumps(files))

        watched_files = {os.path.realpath(f) for f in files}
        regexes = [ "^" + f + "$" for f in watched_files]
        dirs_to_watch = {os.path.dirname(f) for f in watched_files}

        handler = _RuleHandler(self.rule_engine, regexes)
        observer = Observer()

        for d in dirs_to_watch:
            observer.schedule(handler, d, recursive=False)

        observer.start()

        try:
            while observer.is_alive():
                observer.join(timeout=Configs.instance.thread_timeout)
        except KeyboardInterrupt:
            pass
        finally:
            observer.stop()
            observer.join()


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
    cli.loop()


if __name__ == "__main__":
    main()
