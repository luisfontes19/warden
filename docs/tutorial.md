# Warden — Getting Started

This guide walks you through installing Warden and writing your first rule.
For practical use-case examples, see [examples.md](examples.md).
For the full rule syntax, see [rules.md](rules.md).

---

## 1. Installation

### Fleet deployment (macOS — recommended)

For managed Mac fleets the recommended flow is a two-step MDM push:

**Step 1 — Push the installer package**

Download the latest `warden-<version>.pkg` from the
[GitHub Releases page](https://github.com/luisfontes19/warden/releases) and
deploy it to your devices through your MDM solution (Jamf, Kandji, Mosyle,
Intune, etc.) as a standard Package policy.

The package:
- Installs the `warden` binary to `/usr/local/bin/warden` (admin-only, `750`)
- Installs the LaunchDaemon plist to `/Library/LaunchDaemons/`
- Starts the Warden service automatically

**Step 2 — Push the managed configuration profile**

After the package is installed, push a `.mobileconfig` profile containing the
Warden managed policy (see [MDM Configuration](mdm.md)). This tells Warden
where to download rules, which signing key to use, and how often to refresh.
Warden picks up the policy automatically on the next startup.

---

### Local / development install

Download the binary for your platform from the
[GitHub Releases page](https://github.com/luisfontes19/warden/releases) and
place it somewhere on your `PATH` (e.g. `/usr/local/bin/warden`).

Verify the install:

```bash
warden --help
```

---

## 2. Your first rule

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

## 3. Running Warden

In production, Warden is intended to run as a background service configured
entirely through your MDM solution — no command-line arguments needed. The
[MDM policy](mdm.md) tells Warden which rules to load (via `rules-url` or
inline `rules`), and Warden starts enforcing them automatically on startup.
See [MDM Configuration & Bundle Signing](mdm.md) for the full deployment guide.

For local development and testing, you can pass rules directly on the command line.

Load a single rules file:

```bash
warden -r my-rules.yml
```

Load a folder of rules:

```bash
warden -p my-rules/
```

Load multiple files:

```bash
warden -r team-rules.yml -r security-rules.yml
```

When no `-r` or `-p` flags are provided, Warden relies entirely on the MDM
configuration. If a managed policy is present, it downloads and applies the
configured rules automatically — no extra arguments required.

Warden watches every file referenced in the loaded rules. When a watched file is
created or modified, the matching rules are evaluated and their actions are
applied immediately.

Press `Ctrl+C` to stop.

---

## 4. Testing rules before deploying

Use the `test` command to run a rule against a file and see what Warden would do:

```bash
warden test -r my-rules.yml -f notes.txt
```

This enforces the rule and shows which matches were found. To evaluate without
modifying the file, add `--dry-run`:

```bash
warden test -r my-rules.yml -f notes.txt --dry-run
```

Test your rules this way before packaging and deploying them to endpoints.

---

## Next steps

- **[Rule Examples](examples.md)** — walkthroughs for MCP enforcement, secret redaction, webhooks, and more.
- **[Rules Reference](rules.md)** — every pattern type, action, and option.
- **[MDM Configuration & Bundle Signing](mdm.md)** — deploy rules to your fleet.
