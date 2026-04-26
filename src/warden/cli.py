

import argparse
import json
import logging
import os
import threading
from pathlib import Path

from watchdog.events import FileSystemEvent, RegexMatchingEventHandler
from watchdog.observers import Observer

from warden.bundle import (DEFAULT_KEY_PATH, create_bundle, generate_keypair,
                           public_key_to_b64, save_private_key,
                           save_public_key)
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

    def on_deleted(self, event: FileSystemEvent) -> None:
        path = os.path.realpath(event.src_path)
        logging.info("%s deleted", path)
        self.rule_engine.restore_defaults(str(path))
        self.rule_engine.enforce(str(path))


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

    # --- bundle ---
    bundle_parser = subparsers.add_parser("bundle", help="Bundle signing operations")
    bundle_sub = bundle_parser.add_subparsers(dest="bundle_command")

    keygen_parser = bundle_sub.add_parser("keygen", help="Generate a new ML-DSA-65 signing key pair")
    keygen_parser.add_argument(
        "--output",
        dest="key_output",
        metavar="PATH",
        default=None,
        help=f"Path to save the private key (default: {DEFAULT_KEY_PATH})",
    )

    create_parser = bundle_sub.add_parser("create", help="Sign a rules folder and create a zip bundle")
    create_parser.add_argument(
        "--rules-folder",
        dest="folder",
        metavar="FOLDER",
        required=True,
        help="Path to the folder containing rule files to sign",
    )
    create_parser.add_argument(
        "--key",
        dest="key_path",
        metavar="KEY",
        default=None,
        help=f"Path to the private key file (default: {DEFAULT_KEY_PATH})",
    )
    create_parser.add_argument(
        "--output",
        dest="output",
        metavar="OUTPUT",
        required=True,
        help="Output path for the zip bundle",
    )

    return parser


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


def _check_bundle_error_url_configured() -> None:
    """Warn if bundle-error-url is not set in the MDM policy."""
    try:
        handler = Configs.instance.policyHandler
        if handler.is_managed and not Configs.instance.bundle_error_url:
            print(
                "\nWarning: 'bundle-error-url' is not configured in MDM policy.\n"
                "Configure it so agents can report bundle verification failures."
            )
    except AttributeError:
        pass


def _cmd_bundle(args: argparse.Namespace) -> None:
    if args.bundle_command == "keygen":
        mlkem_key, pub_der = generate_keypair()
        key_path = Path(args.key_output) if args.key_output else DEFAULT_KEY_PATH

        save_private_key(mlkem_key, key_path)
        print(f"Private key saved to: {key_path}")
        pub_path = key_path.with_suffix(key_path.suffix + ".pub")
        save_public_key(pub_der, pub_path)
        print(f"Public key saved to:  {pub_path}")

        pub_b64 = public_key_to_b64(pub_der)
        print("\nPublic key (add to MDM policy as 'bundle-signing-public-key'):")
        print(f"  {pub_b64}")
        _check_bundle_error_url_configured()

    elif args.bundle_command == "create":
        folder = Path(args.folder)
        if not folder.is_dir():
            print(f"Error: {folder} is not a directory")
            return

        key_path = Path(args.key_path) if args.key_path else DEFAULT_KEY_PATH
        if not key_path.exists():
            print(f"Error: private key not found at {key_path}")
            print("Run 'warden bundle keygen' first, or pass --key PATH")
            return

        output = Path(args.output)
        create_bundle(folder, key_path, output)
        print(f"Bundle created: {output}")
        signed = sum(
            1 for f in folder.rglob("*") if f.is_file() and f.name != Configs.SIGNATURES_FILE
        )
        print(f"Signed {signed} file(s)")
        _check_bundle_error_url_configured()

    else:
        print("Usage: warden bundle [keygen|create]")


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


def _start_refresh_thread(engine: RuleEngine, observer) -> threading.Thread | None:
    refresh_interval = Configs.instance.refresh_interval
    if not refresh_interval:
        return None

    stop_event = threading.Event()

    def _refresh_loop() -> None:
        while not stop_event.wait(refresh_interval * 60):
            logging.info("Refreshing policy and rules (every %d min)", refresh_interval)
            try:
                Configs.load_configs()
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
    Configs.instance.log_configs()

    if args.thread_timeout is not None:
        Configs.instance.thread_timeout = args.thread_timeout

    if args.command == "test":
        _cmd_test(args)
    elif args.command == "run":
        _cmd_run(args)
    elif args.command == "bundle":
        _cmd_bundle(args)
    else:
        # No subcommand: default to running with MDM/managed rules
        args.rule_files = []
        args.rules_path = None
        _cmd_run(args)


if __name__ == "__main__":
    main()
