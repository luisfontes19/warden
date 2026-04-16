

import argparse
import json
import logging
import os
import threading

from watchdog.events import FileSystemEvent, RegexMatchingEventHandler
from watchdog.observers import Observer

from warden.configs import Configs
from warden.engine.rules_engine import RuleEngine


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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="warden",
        description="Warden - file rule enforcement",
    )

    # Global params
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="Enable debug logging",
    )

    parser.add_argument(
        "--thread-timeout",
        type=int,
        default=None,
        help="Thread join timeout in seconds",
    )

    subparsers = parser.add_subparsers(dest="command")

    # --- test ---
    test_parser = subparsers.add_parser("test", help="Test a rule against a file")
    test_parser.add_argument(
        "-r",
        dest="rule_file",
        required=True,
        metavar="RULE_FILE",
        help="Path to the rule file",
    )
    test_parser.add_argument(
        "-f",
        dest="file",
        required=True,
        metavar="FILE",
        help="Path to the file to run the rule against",
    )
    test_parser.add_argument(
        "-d",
        "--dry-run",
        action="store_true",
        default=False,
        help="Dry run: evaluate only, do not enforce",
    )

    # --- run ---
    run_parser = subparsers.add_parser(
        "run", help="Run rules and monitor file changes"
    )
    run_parser.add_argument(
        "-r",
        dest="rule_files",
        action="append",
        metavar="RULE_FILE",
        default=[],
        help="Path to a rules file (can be specified multiple times)",
    )
    run_parser.add_argument(
        "-p",
        dest="rules_path",
        metavar="DIR",
        default=None,
        help="Path to a directory containing rule files",
    )

    return parser


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


def _cmd_test(args: argparse.Namespace) -> None:
    engine = RuleEngine(rule_files=[args.rule_file])

    if args.dry_run:
        matches = engine.evaluate_file(args.file)
    else:
        matches = engine.enforce(args.file)

    if not matches:
        print("No matches found.")
        return

    for m in matches:
        print(m)


def _start_refresh_thread(engine: RuleEngine, observer: Observer) -> threading.Thread | None:
    refresh_interval = Configs.instance.refresh_interval
    if not refresh_interval:
        return None

    stop_event = threading.Event()

    def _refresh_loop() -> None:
        while not stop_event.wait(refresh_interval * 60):
            logging.info("Refreshing policy and rules (every %d min)", refresh_interval)
            try:
                Configs.instance.policyHandler.init()
                engine.reload()

                new_files = engine.monitoring_files()
                logging.info("Monitoring files after refresh: %s", json.dumps(new_files))

                # Update observer schedules
                observer.unschedule_all()
                watched = {os.path.realpath(f) for f in new_files}
                regexes = ["^" + f + "$" for f in watched]
                dirs = {os.path.dirname(f) for f in watched}

                handler = _RuleHandler(engine, regexes)
                for d in dirs:
                    observer.schedule(handler, d, recursive=False)
            except Exception:
                logging.exception("Error during policy refresh")

    t = threading.Thread(target=_refresh_loop, daemon=True, name="policy-refresh")
    t._stop_event = stop_event  # type: ignore[attr-defined]
    t.start()
    logging.info("Policy refresh thread started (interval: %d min)", refresh_interval)
    return t


def _cmd_run(args: argparse.Namespace) -> None:
    engine = RuleEngine(
        folder=args.rules_path,
        rule_files=args.rule_files or None,
    )

    files = engine.monitoring_files()
    logging.info("Monitoring files: %s", json.dumps(files))

    if not files:
        logging.warning("No files to monitor. Check your rules.")


    watched_files = {os.path.realpath(f) for f in files}
    regexes = ["^" + f + "$" for f in watched_files]
    dirs_to_watch = {os.path.dirname(f) for f in watched_files}

    handler = _RuleHandler(engine, regexes)
    observer = Observer()

    for d in dirs_to_watch:
        observer.schedule(handler, d, recursive=False)

    observer.start()
    refresh_thread = _start_refresh_thread(engine, observer)

    try:
        while observer.is_alive():
            observer.join(timeout=Configs.instance.thread_timeout)
    except KeyboardInterrupt:
        pass
    finally:
        if refresh_thread and hasattr(refresh_thread, "_stop_event"):
            refresh_thread._stop_event.set()  # type: ignore[attr-defined]
        observer.stop()
        observer.join()


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    _configure_logging(args.verbose)

    Configs.load_configs()

    if args.thread_timeout is not None:
        Configs.instance.thread_timeout = args.thread_timeout

    if args.command == "test":
        _cmd_test(args)
    elif args.command == "run":
        _cmd_run(args)
    else:
        # No subcommand: default to running with MDM/managed rules
        args.rule_files = []
        args.rules_path = None
        _cmd_run(args)


if __name__ == "__main__":
    main()
