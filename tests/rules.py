from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path
import traceback
from typing import Any

from warden.rules_engine import ActionResult, RuleFile, Match

RULES_DIR = Path(__file__).parent / "rules"

W = 64


def _scenario_dirs() -> list[Path]:
    return sorted(d for d in RULES_DIR.iterdir() if d.is_dir())


def _load_outcome(path: Path) -> Any:
    if path.suffix == ".json":
        return json.loads(path.read_bytes())
    return path.read_text(encoding="utf-8")


def _normalise_actual(value: Any, suffix: str) -> Any:
    if suffix == ".json":
        return json.loads(value) if isinstance(value, str) else value
    return value if isinstance(value, str) else json.dumps(value, indent=2)


def _fmt(value: Any) -> str:
    text = repr(value)
    return text if len(text) <= 80 else text[:77] + "..."


def run_scenario(rule_dir: Path) -> bool:
    print(f"\n╔{'═' * (W - 2)}╗")
    print(f"║  📁 Scenario: {rule_dir.name:<{W - 18}}║")
    print(f"╚{'═' * (W - 2)}╝")

    rule_yml = rule_dir / "rules.yml"
    if not rule_yml.exists():
        print(f"  ❌ missing rules.yml")
        return False

    sample = next((f for f in rule_dir.iterdir() if f.stem == "sample"), None)
    outcome = next((f for f in rule_dir.iterdir() if f.stem == "outcome"), None)

    if sample is None:
        print(f"  ❌ no sample.* file found")
        return False
    if outcome is None:
        print(f"  ❌ no outcome.* file found")
        return False

    rules = RuleFile(rule_yml).rules
    print(f"  📋 rules: {len(rules)}  |  sample: {sample.name}  |  outcome: {outcome.name}")
    print(f"  {'·' * (W - 4)}")

    with tempfile.NamedTemporaryFile(suffix=sample.suffix, delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        shutil.copy2(sample, tmp_path)

        result: Any = None
        result_from_actions = False

        for rule in rules:
            matches: list[Match] = rule.evaluate_against_file(str(tmp_path))

            if not matches:
                print(f"  ⬜ {rule.rule_id!r}  — no match")
                continue

            print(f"  🎯 {rule.rule_id!r}  ({len(matches)} match(es))")
            if rule.description:
                print(f"      desc    : {rule.description}")
            for m in matches:
                print(f"      content : {_fmt(m.matched_content)}")

            new_content = rule.apply_actions(matches)

            if isinstance(new_content, ActionResult):
                if new_content is ActionResult.FILE_DELETED:
                    print(f"      ⚙️  delete-file action → file deleted")
                    tmp_path.unlink(missing_ok=True)
                    result = ActionResult.FILE_DELETED
                elif new_content is ActionResult.CODE_HANDLED:
                    print(f"      ⚙️  code handler invoked → reading file result")
                    result = tmp_path.read_text(encoding="utf-8") if tmp_path.exists() else ActionResult.FILE_DELETED
                elif new_content is ActionResult.REQUEST_SENT:
                    print(f"      ⚙️  request action sent → reading file result")
                    result = tmp_path.read_text(encoding="utf-8") if tmp_path.exists() else ActionResult.FILE_DELETED
                result_from_actions = True
            elif new_content is not None:
                print(f"      ⚙️  actions applied → result updated")
                tmp_path.write_text(new_content, encoding="utf-8")
                result = new_content
                result_from_actions = True
            else:
                print(f"      ℹ️  no actions — using matched_content as result")
                contents = [m.matched_content for m in matches]
                result = contents[0] if len(contents) == 1 else contents

        if result is None:
            print(f"\n  ❌ no rule produced a result")
            return False

        expected = _load_outcome(outcome)
        actual = _normalise_actual(result, outcome.suffix)
        source = "actions" if result_from_actions else "matched_content"

        print(f"\n  🔍 comparing {source} → {outcome.name}")
        print(f"  {'·' * (W - 4)}")
        print(f"  expected : {_fmt(expected)}")
        print(f"  actual   : {_fmt(actual)}")

        if actual == expected:
            print(f"\n  ✅ PASS — output matches {outcome.name}")
            return True
        else:
            print(f"\n  ❌ FAIL — output does NOT match {outcome.name}")
            return False

    except Exception as exc:
        traceback.print_exc()
        return False
    finally:
        tmp_path.unlink(missing_ok=True)


def main() -> None:
    scenarios = _scenario_dirs()
    print(f"\n🧪 Found {len(scenarios)} scenario(s) in {RULES_DIR.relative_to(Path.cwd())}")

    results: dict[str, bool] = {}
    for d in scenarios:
        results[d.name] = run_scenario(d)

    print(f"\n{'═' * W}")
    print(f"  📊 Summary")
    print(f"{'─' * W}")
    for name, passed in results.items():
        icon = "✅" if passed else "❌"
        print(f"  {icon}  {name}")
    print(f"{'═' * W}\n")

    if not all(results.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()

