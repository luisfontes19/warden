# Warden — Getting Started Tutorial

This tutorial walks you through installing Warden and writing your first rules.
By the end you will have a running file watcher that automatically enforces
policies on your local files.

For the full rule syntax, see [rules.md](rules.md).

---

## Table of Contents

1. [Installation](#1-installation)
2. [Your first rule — remove a forbidden word](#2-your-first-rule--remove-a-forbidden-word)
3. [Running Warden](#3-running-warden)
4. [Use case: lock down MCP servers in VS Code](#4-use-case-lock-down-mcp-servers-in-vs-code)
5. [Use case: redact hardcoded secrets](#5-use-case-redact-hardcoded-secrets)
6. [Use case: delete a file on sight](#6-use-case-delete-a-file-on-sight)
7. [Use case: send a webhook when a rule matches](#7-use-case-send-a-webhook-when-a-rule-matches)
8. [Use case: custom Python logic](#8-use-case-custom-python-logic)
9. [Tips and next steps](#9-tips-and-next-steps)

---

## 1. Installation

Warden uses **uv** for dependency management. Clone the repository and install:

```bash
git clone <repo-url> && cd referee
uv sync
```

Verify it works:

```bash
uv run src/warden/cli.py --help
```

---

## 2. Your first rule — remove a forbidden word

Create a file called `my-rules.yml`:

```yaml
version: 1
rules:
  - id: remove-todo
    description: Removes any TODO comments so they don't ship to production
    file: notes.txt
    patterns:
      - contains: "TODO"
    actions:
      - delete:
```

Now create a test file called `notes.txt`:

```
Buy milk
TODO fix the login bug
Call dentist
TODO update docs
```

This rule watches `notes.txt`. Whenever the file contains the substring `TODO`,
Warden deletes every occurrence. After enforcement the file becomes:

```
Buy milk
 fix the login bug
Call dentist
 update docs
```

> **Tip:** The `delete` action removes the exact matched text — in this case
> the literal string `TODO`. It does not remove the entire line.

---

## 3. Running Warden

Start Warden with your rules file:

```bash
uv run src/warden/cli.py -r my-rules.yml
```

Warden will watch every file referenced in your rules. When a watched file is
created or modified, the matching rules are evaluated and their actions are
applied automatically.

You can pass multiple `-r` flags to load several rule files:

```bash
uv run src/warden/cli.py -r team-rules.yml -r security-rules.yml
```

Warden also loads any `.yml` files from its default rules directory
(`~/.local/share/warden/policy-rules` on Linux,
`~/Library/Application Support/warden/policy-rules` on macOS).
The `-r` flag adds rules on top of those defaults.

Press `Ctrl+C` to stop the watcher.

---

## 4. Use case: lock down MCP servers in VS Code

**Problem:** Developers can add arbitrary MCP servers to their VS Code or
Cursor configuration. You want only an approved set of servers to remain.

**Solution:** Watch the MCP config files and filter out unapproved entries
using a `jq` pattern and action.

```yaml
version: 1
rules:
  - id: approved-mcp-only
    description: Keeps only the approved youtube MCP server
    file:
      - .vscode/mcp.json
      - .cursor/mcp.json
    filetype: json
    patterns:
      - jq: |
          [.mcpServers | to_entries[]
            | select((.value.args // [])
              | contains(["github:anaisbetts/mcp-youtube"]) | not)
            | .key]
    actions:
      - replace:
          jq: |
            .mcpServers |= with_entries(
              select(.value.args // []
                | contains(["github:anaisbetts/mcp-youtube"]))
            )
```

**How it works:**

1. The `jq` pattern collects every MCP server whose args do NOT include the
   approved package. If the result is a non-empty list the rule matches.
2. The `replace` action rewrites the file, keeping only the approved entries.

**Before** (`.vscode/mcp.json`):

```json
{
  "mcpServers": {
    "brave-search": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-brave-search"]
    },
    "youtube": {
      "command": "npx",
      "args": ["-y", "github:anaisbetts/mcp-youtube"]
    }
  }
}
```

**After:**

```json
{
  "mcpServers": {
    "youtube": {
      "command": "npx",
      "args": ["-y", "github:anaisbetts/mcp-youtube"]
    }
  }
}
```

---

## 5. Use case: redact hardcoded secrets

**Problem:** A config file may accidentally contain AWS access keys or API
tokens that should never be committed.

**Solution:** Use a regex pattern to detect secret-shaped strings and replace
them.

```yaml
version: 1
rules:
  - id: redact-aws-keys
    description: Replaces AWS access keys with a placeholder
    file: config/app.env
    filetype: text
    patterns:
      - match: "AKIA[0-9A-Z]{16}"
    actions:
      - replace: "REDACTED_AWS_KEY"
```

Every time `config/app.env` is saved with a string that looks like an AWS
access key, Warden replaces it with `REDACTED_AWS_KEY`.

You can stack multiple rules in the same file to catch different secret
patterns:

```yaml
version: 1
rules:
  - id: redact-aws-keys
    file: config/app.env
    patterns:
      - match: "AKIA[0-9A-Z]{16}"
    actions:
      - replace: "REDACTED_AWS_KEY"

  - id: redact-generic-tokens
    file: config/app.env
    patterns:
      - match: "(?i)token\\s*=\\s*['\"]?[A-Za-z0-9_\\-]{32,}['\"]?"
    actions:
      - replace: "token=REDACTED"
```

---

## 6. Use case: delete a file on sight

**Problem:** A specific config file should never exist in the project. If
someone creates it, you want it removed immediately.

**Solution:** Use the `exists` pattern with the `delete-file` action.

```yaml
version: 1
rules:
  - id: no-local-overrides
    description: Deletes the local override config whenever it appears
    file: config/local-overrides.json
    patterns:
      - exists:
    actions:
      - delete-file:
```

As soon as `config/local-overrides.json` is created, Warden deletes it.

You can combine this with a second rule that recreates the file with safe
defaults:

```yaml
version: 1
rules:
  - id: delete-bad-config
    file: config/local-overrides.json
    patterns:
      - exists:
    actions:
      - delete-file:

  - id: recreate-safe-config
    file: config/local-overrides.json
    patterns:
      - not-exists:
    actions:
      - add: '{"debug": false, "env": "production"}'
```

Rules are evaluated in order, so the file is first deleted then recreated with
the safe content.

---

## 7. Use case: send a webhook when a rule matches

**Problem:** You want to notify a Slack channel or an external service whenever
a policy violation is detected, without modifying the file.

**Solution:** Use the `request` action.

```yaml
version: 1
rules:
  - id: notify-secret-leak
    description: Alerts the security channel when a secret pattern is found
    file: config/app.env
    patterns:
      - match: "AKIA[0-9A-Z]{16}"
    actions:
      - request:
          url: https://hooks.slack.com/services/T00/B00/xxxx
          method: POST
          headers:
            Content-Type: application/json
          body: |
            {
              "text": "Rule ${{rule_id}} triggered on ${{file}}",
              "matched": "${{matched_content}}"
            }
```

The `request` action does not modify the file. You can combine it with other
actions — for example, redact the secret *and* send a notification:

```yaml
    actions:
      - replace: "REDACTED"
      - request:
          url: https://hooks.slack.com/services/T00/B00/xxxx
          method: POST
          headers:
            Content-Type: application/json
          body: '{"text": "Secret redacted in ${{file}} by rule ${{rule_id}}"}'
```

### Placeholders

Inside `request` fields you can use `${{…}}` placeholders:

| Placeholder          | Value                                      |
|----------------------|--------------------------------------------|
| `${{rule_id}}`       | The rule's `id`                            |
| `${{description}}`   | The rule's `description`                   |
| `${{file}}`          | Path to the matched file                   |
| `${{matched_content}}` | The content extracted by the pattern     |
| `${{file_content}}`  | The full file content                      |
| `${{json(matches)}}` | All match objects serialised as JSON       |

---

## 8. Use case: custom Python logic

**Problem:** The built-in actions are not enough — you need arbitrary
transformation logic.

**Solution:** Use the `code` action to run a Python script.

Create `handlers/normalize.py` next to your rules file:

```python
def handler(filename):
    with open(filename, encoding="utf-8") as f:
        content = f.read()

    # Normalize line endings and strip trailing whitespace
    lines = content.splitlines()
    cleaned = "\n".join(line.rstrip() for line in lines) + "\n"

    with open(filename, "w", encoding="utf-8") as f:
        f.write(cleaned)
```

Reference it from your rule:

```yaml
version: 1
rules:
  - id: normalize-whitespace
    description: Strips trailing whitespace and normalizes line endings
    file: src/main.py
    actions:
      - code: handlers/normalize.py
```

Since no `patterns` are specified the rule matches unconditionally — the
handler runs every time the file changes.

> **Security note:** The code path must stay within the rules directory.
> Warden rejects path-traversal attempts like `../../etc/passwd`.

---

## 9. Tips and next steps

- **Combine patterns with `or` and `and`** to build precise conditions.
  An `or` matches when any sub-pattern is true; an `and` (or a plain list)
  matches when all are true.

  ```yaml
  patterns:
    - or:
        - contains: "DEBUG"
        - contains: "TRACE"
        - match: "(?i)verbose\\s*=\\s*true"
  ```

- **Multiple files per rule.** Pass an array to `file:` to apply the same
  policy to several paths at once.

- **Chain actions.** Actions execute in order on the current file state, so
  you can delete, then add, then send a notification — all in one rule.

- **Test your rules.** Put sample input and expected output files in a folder
  and run `task test-rules` to verify your rules produce the right result
  before deploying them.

- **Full reference.** See [rules.md](rules.md) for every pattern, action, and
  option available.
