# Warden — Getting Started

This guide covers the normal Warden rollout flow: install with MDM, write a
first rule, test it, and then deploy rules to endpoints.

For practical use-case walkthroughs, see [examples.md](examples.md).
For full rule syntax, see [rules_reference.md](rules_reference.md).

---

## 1. Install Warden with MDM

Warden installation on managed macOS devices is a two-step push:

1. Push the latest `warden-<version>.pkg` from
  [GitHub Releases](https://github.com/luisfontes19/warden/releases) (or in the Github Actions outputs while it is still in pre-release)
2. Push a managed `.mobileconfig` policy for Warden

---

## 2. Write your first rule

Rules are YAML files. Create `my-rules.yml`:

```yaml
version: 1
rules:
  - id: remove-todo
    description: Removes TODO comments from the file
    file: notes.txt
    patterns:
      - contains: "TODO"
    actions:
      - delete:
```

Create a test file `notes.txt`:

```
Buy milk
TODO fix the login bug
Call dentist
TODO update docs
```

This rule watches `notes.txt`. Whenever the file is saved with the substring `TODO`, Warden removes every occurrence. After enforcement:

```
Buy milk
 fix the login bug
Call dentist
 update docs
```

> The `delete` action removes the exact matched text — in this case the literal string `TODO`. It does not delete the whole line.

---

## 3. Test your rule before rollout

Use the test command to run a rule against a file and inspect the result.

Run a one-shot test with one rules file:

```bash
warden test -r my-rules.yml -f notes.txt
```

This enforces the rule and shows what matched. To evaluate without modifying
the file, add `--dry-run`:

```bash
warden test -r my-rules.yml -f notes.txt --dry-run
```

Use this flow to validate rule behavior before adding rules to your managed
policy or signed bundle.

---

## 4. Roll out rules to endpoints

After validation, deploy rules through the managed policy:

- Use `rules-url` for hosted signed bundles
- Use `rules` for inline base64 rule entries
- Use both for a baseline-plus-dynamic strategy

See [MDM Configuration & Bundle Signing](mdm_configuration.md) for the policy
fields and signing workflow.

---

## Next steps

- **[Rule Examples](examples.md)** — walkthroughs for MCP enforcement, secret redaction, webhooks, and more.
- **[Rules Reference](rules_reference.md)** — every pattern type, action, and option.
- **[MDM Configuration & Bundle Signing](mdm_configuration.md)** — deploy rules to your fleet.
