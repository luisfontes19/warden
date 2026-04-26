# Warden — Rule Examples

All examples on this page are validated against real test files. They progress
from the simplest possible rule to complex multi-condition JSON policies.

For the full pattern and action syntax, see [rules_reference.md](rules_reference.md).

---

## 1. Replace a specific value

**Scenario:** A config file has `debug=true`. Whenever it appears, reset it to `debug=false`.

```yaml
version: 1
rules:
  - id: disable-debug
    description: Replaces debug=true with debug=false
    file: /etc/myapp/config.ini
    filetype: text
    patterns:
      - contains: "debug=true"
    actions:
      - replace: "debug=false"
```

| Before | After |
|---|---|
| `log_level=info` | `log_level=info` |
| `debug=true` | `debug=false` |
| `verbose=false` | `verbose=false` |

The `contains` pattern matches when the exact string is present anywhere in the
file. The `replace` action swaps every occurrence with the new value.

---

## 2. Delete unwanted text

**Scenario:** Strip a prefix from lines so only the useful content remains.

```yaml
version: 1
rules:
  - id: remove-todo-prefix
    description: Strips the "TODO:" prefix from lines, leaving the rest of the text
    file: /etc/myapp/notes.txt
    filetype: text
    patterns:
      - contains: "TODO: "
    actions:
      - delete:
```

| Before | After |
|---|---|
| `line one` | `line one` |
| `TODO: fix the login bug` | `fix the login bug` |
| `line two` | `line two` |
| `TODO: update the docs` | `update the docs` |

`delete` with no value removes every occurrence of the matched text. The rest of
each line is untouched.

---

## 3. Redact secrets with a regex

**Scenario:** A config or env file may be saved with an AWS access key. Detect
and redact it automatically.

```yaml
version: 1
rules:
  - id: redact-aws-key
    description: Redacts AWS access key patterns (AKIA...)
    file: /etc/myapp/app.env
    filetype: text
    patterns:
      - match: "AKIA[0-9A-Z]{16}"
    actions:
      - replace: "REDACTED"
```

| Before | After |
|---|---|
| `AWS_ACCESS_KEY=AKIAIOSFODNN7EXAMPLE` | `AWS_ACCESS_KEY=REDACTED` |
| `AWS_REGION=us-east-1` | `AWS_REGION=us-east-1` |

`match` applies a Python regex. The first matching substring becomes
`matched_content`, and `replace` substitutes it.

---

## 4. Add a required setting if it is missing

**Scenario:** Ensure a mandatory security setting exists in the file. If it is
absent, append it.

```yaml
version: 1
rules:
  - id: ensure-strict-security
    description: Appends security=strict if the setting is missing
    file: /etc/myapp/config.ini
    filetype: text
    patterns:
      - not-contains: "security=strict"
    actions:
      - add: "security=strict\n"
```

| Before | After |
|---|---|
| `log_level=info` | `log_level=info` |
| `debug=false` | `debug=false` |
| *(missing)* | `security=strict` |

`not-contains` matches when the string is **absent**. The rule fires only once
— on the next save after the setting is already present, `not-contains` no
longer matches and the rule does nothing.

---

## 5. Enforce a JSON boolean value

**Scenario:** A JSON config has a `debug` flag. Whenever it is `true`, set it
back to `false`.

```yaml
version: 1
rules:
  - id: disable-debug-mode
    description: Sets debug to false if it is currently true
    file: ~/.config/myapp/settings.json
    filetype: json
    patterns:
      - jq: '.debug == true'
    actions:
      - replace:
          jq: '.debug = false'
```

**Before:**
```json
{ "debug": true, "env": "production", "port": 8080 }
```

**After:**
```json
{ "debug": false, "env": "production", "port": 8080 }
```

`jq` patterns match when the expression returns a truthy value. The `replace`
action's `jq` expression receives the full file object and returns the modified
version.

---

## 6. Enforce a JSON string value

**Scenario:** A `env` field must always be `"production"`. If a user changes it
to anything else, reset it.

```yaml
version: 1
rules:
  - id: enforce-production-env
    description: Sets the env field to production if it is anything else
    file: ~/.config/myapp/settings.json
    filetype: json
    patterns:
      - jq: '.env != "production"'
    actions:
      - replace:
          jq: '.env = "production"'
```

**Before:**
```json
{ "env": "development", "port": 3000, "log_level": "debug" }
```

**After:**
```json
{ "env": "production", "port": 3000, "log_level": "debug" }
```

---

## 7. Remove a forbidden key entirely

**Scenario:** Users may add an `allowAllCommands` flag to bypass permission
prompts. Remove it whenever it appears.

```yaml
version: 1
rules:
  - id: remove-allow-all-commands
    description: Removes the allowAllCommands flag to restore permission prompts
    file: ~/.claude/settings.json
    filetype: json
    patterns:
      - jq: '.allowAllCommands == true'
    actions:
      - replace:
          jq: 'del(.allowAllCommands)'
```

**Before:**
```json
{ "allowAllCommands": true, "theme": "dark", "fontSize": 14 }
```

**After:**
```json
{ "theme": "dark", "fontSize": 14 }
```

`del(.key)` is standard jq syntax for removing a key. The rule only fires when
the key is present and set to `true`.

---

## 8. MCP server allowlist

**Scenario:** AI tool configs allow users to add arbitrary MCP servers. Enforce
an allowlist so only `github` and `postgres` can remain.

```yaml
version: 1
rules:
  - id: mcp-allowlist
    description: Removes any MCP server not on the approved list (github, postgres)
    file:
      - ~/.claude/claude_desktop_config.json
      - ~/.cursor/mcp.json
      - .vscode/mcp.json
    filetype: json
    patterns:
      - jq: |
          [.mcpServers | to_entries[]
            | select(.key != "github" and .key != "postgres")
            | .key] | length > 0
    actions:
      - replace:
          jq: |
            .mcpServers |= with_entries(
              select(.key == "github" or .key == "postgres")
            )
```

**Before:**
```json
{
  "mcpServers": {
    "github":       { "command": "npx", "args": ["-y", "@modelcontextprotocol/server-github"] },
    "brave-search": { "command": "npx", "args": ["-y", "@modelcontextprotocol/server-brave-search"] },
    "postgres":     { "command": "npx", "args": ["-y", "@modelcontextprotocol/server-postgres"] },
    "unknown-tool": { "command": "npx", "args": ["-y", "some-unapproved-package"] }
  }
}
```

**After:**
```json
{
  "mcpServers": {
    "github":   { "command": "npx", "args": ["-y", "@modelcontextprotocol/server-github"] },
    "postgres": { "command": "npx", "args": ["-y", "@modelcontextprotocol/server-postgres"] }
  }
}
```

The `jq` pattern collects every server key not in the approved list. If any
exist, the `replace` action rewrites `mcpServers` keeping only approved entries.
To expand the allowlist, add more conditions: `select(.key == "github" or .key == "postgres" or .key == "slack")`.

---

## 9. Extract a nested value, then enforce it

**Scenario:** A deeply nested field (`database.host`) must never be set to
`"localhost"` in production configs.

```yaml
version: 1
rules:
  - id: enforce-production-db-host
    description: Replaces localhost database host with the production hostname
    file: /etc/myapp/config.json
    filetype: json
    patterns:
      - nested:
          - jq: '.database.host'
          - equals: "localhost"
    actions:
      - replace:
          jq: '.database.host = "db.production.internal"'
```

**Before:**
```json
{
  "database": { "host": "localhost", "port": 5432, "name": "myapp" },
  "cache": { "host": "redis.internal", "port": 6379 }
}
```

**After:**
```json
{
  "database": { "host": "db.production.internal", "port": 5432, "name": "myapp" },
  "cache": { "host": "redis.internal", "port": 6379 }
}
```

`nested` chains patterns: the first `jq` extracts `.database.host`, and
`equals` checks the extracted value. If the chain matches, the `replace` action
updates the original object.

---

## 10. Conditional rule — AND gate

**Scenario:** A config is critically misconfigured only when `mode` is `"test"`
**and** `auth` is `"disabled"` at the same time. Neither condition alone is
enough to trigger the fix.

```yaml
version: 1
rules:
  - id: fix-insecure-test-config
    description: Resets auth and mode only when both are simultaneously in insecure test state
    file: /etc/myapp/server.json
    filetype: json
    patterns:
      - and:
          - jq: '.mode == "test"'
          - jq: '.auth == "disabled"'
    actions:
      - replace:
          jq: '.auth = "required" | .mode = "production"'
```

**Before:**
```json
{ "mode": "test", "auth": "disabled", "port": 8080 }
```

**After:**
```json
{ "mode": "production", "auth": "required", "port": 8080 }
```

The `and` pattern acts as a gate: only the specific dangerous combination
triggers the correction. If either condition is false, the rule does nothing.

---

## 11. Chain patterns — implicit AND

**Scenario:** Enforce `env: "production"` only when the key already exists in
the file. Files that don't have an `env` field are left untouched.

```yaml
version: 1
rules:
  - id: enforce-production-env
    description: Sets env to production when the key exists but is not already production
    file: config/deploy.json
    filetype: json
    patterns:
      - jq: 'has("env")'
      - jq: '.env != "production"'
    actions:
      - replace:
          jq: '.env = "production"'
```

**Before:**
```json
{ "env": "development", "port": 3000, "log_level": "debug" }
```

**After:**
```json
{ "env": "production", "port": 3000, "log_level": "debug" }
```

A list of patterns is an implicit AND: every item must match in order. Each
pattern is evaluated against the original file content. Files without an `env`
key fail the first check and the rule does not fire.

---

## 12. Require a minimum Node.js version

**Scenario:** All `package.json` files must declare `engines.node >= 20`. If the
field is missing or set to an earlier version, enforce it.

```yaml
version: 1
rules:
  - id: enforce-node-version
    description: Ensures engines.node is set to >=20
    file: package.json
    filetype: json
    patterns:
      - jq: '.engines.node != ">=20"'
    actions:
      - replace:
          jq: '.engines.node = ">=20"'
```

**Before:**
```json
{ "name": "my-app", "version": "1.0.0", "engines": { "node": ">=18" } }
```

**After:**
```json
{ "name": "my-app", "version": "1.0.0", "engines": { "node": ">=20" } }
```

---

## 13. Delete a forbidden file on creation

**Scenario:** A specific config file must never exist on a managed machine.
Delete it the moment it appears, then leave a placeholder so the user knows what
happened.

```yaml
version: 1
rules:
  - id: remove-forbidden-mcp-config
    description: Deletes the MCP config file as soon as it appears
    file: .cursor/mcp.json
    patterns:
      - exists:
    actions:
      - delete-file:

  - id: notify-deleted-mcp-config
    description: Writes a notice after the MCP config is deleted
    file: .cursor/mcp.json
    patterns:
      - not-exists:
    actions:
      - add: "mcp config removed by policy\n"
```

The first rule fires when the file exists and deletes it. The second rule fires
on the next evaluation while the file is still absent, leaving a one-line
placeholder. Once the placeholder exists, `not-exists` no longer matches and
neither rule fires again.

---

## 14. Run a Python code handler

**Scenario:** Enforce that a managed text file stays sorted and de-duplicated.
A Python handler reads the file and rewrites it in the required form.

```yaml
version: 1
rules:
  - id: sort-and-deduplicate-lines
    description: Sorts and deduplicates lines in the file using a Python handler
    file: /etc/myapp/allowed-hosts.txt
    filetype: text
    actions:
      - code: handlers/sort_lines.py
```

`handlers/sort_lines.py` (in the same rules bundle):

```python
def handler(filename):
    with open(filename, encoding="utf-8") as f:
        lines = f.read().splitlines()
    sorted_unique = sorted(set(line for line in lines if line))
    with open(filename, "w", encoding="utf-8") as f:
        f.write("\n".join(sorted_unique) + "\n")
```

| Before | After |
|---|---|
| `banana` | `apple` |
| `apple` | `banana` |
| `cherry` | `cherry` |
| `apple` | `date` |
| `banana` | |
| `date` | |
| `cherry` | |

Code handlers receive the full file path and can read, transform, and write it
freely. When bundle signing is enabled, the handler file must be included in the
bundle so its signature is verified before execution.

---

## 15. Send a webhook on policy violation

**Scenario:** When a forbidden keyword appears in a config file, send an HTTP
notification to a webhook with the rule ID, file path, and matched content.

```yaml
version: 1
rules:
  - id: notify-on-forbidden-word
    description: Sends a POST request when a forbidden word is found
    file: /etc/myapp/config.ini
    filetype: text
    patterns:
      - contains: "pariatur"
    actions:
      - request:
          url: "https://hooks.example.com/warden-alerts"
          method: POST
          headers:
            Content-Type: application/json
            X-Rule-Id: "${{rule_id}}"
          body: |
            {"rule": "${{rule_id}}", "file": "${{matches[0].file}}", "matched": "${{matched_content}}"}
```

The `request` action supports `${{placeholder}}` template variables. See
[rules_reference.md §5](rules_reference.md#5-placeholders) for the full list of available variables.

The file is **not modified** by a `request` action — use it alongside a
`replace` or `delete` action in the same rule when you need both remediation and
notification.

---

## 16. OR pattern — act on any of several conditions

**Scenario:** Remove any line that contains one of several forbidden words.

```yaml
version: 1
rules:
  - id: remove-blacklisted-words
    description: Removes lines containing "pariatur" or "mollit"
    file: docs/draft.txt
    filetype: text
    patterns:
      - or:
          - contains: pariatur
          - contains: mollit
    actions:
      - delete:
```

| Before | After |
|---|---|
| `line one` | `line one` |
| `word: pariatur` | `line two` |
| `line two` | |
| `word: mollit` | |

`or` matches when **any** sub-pattern matches and sets `matched_content` to
the value from the first matching branch. Here both branches use `contains`, so
the matched needle is deleted from the file.

---

## 17. OR of AND conditions

**Scenario:** A server config is dangerous if EITHER the `admin` role has no
auth, OR the `superuser` role has bypass enabled. Fix both cases with a single
rule.

```yaml
version: 1
rules:
  - id: enforce-secure-role-config
    description: Fixes dangerous role/auth combinations via OR of AND conditions
    file: /etc/myapp/server.json
    filetype: json
    patterns:
      - or:
          - and:
              - jq: '.role == "admin"'
              - jq: '.auth == "none"'
          - and:
              - jq: '.role == "superuser"'
              - jq: '.bypass == true'
    actions:
      - replace:
          jq: '.auth = "required" | .bypass = false'
```

**Before:**
```json
{ "role": "admin", "auth": "none", "bypass": false, "port": 8080 }
```

**After:**
```json
{ "role": "admin", "auth": "required", "bypass": false, "port": 8080 }
```

`or` and `and` can be composed to any depth. This rule fires if either AND
branch matches. The `replace` action always runs against the full file, so it
can fix fields regardless of which branch triggered it.

---

## 18. Deeply nested AND conditions

**Scenario:** Only enforce security settings when ALL four insecure flags are
simultaneously set. Any partial combination should be left alone.

```yaml
version: 1
rules:
  - id: fix-fully-insecure-server
    description: Fixes a server only when ALL four insecure flags are simultaneously set
    file: /etc/myapp/server.json
    filetype: json
    patterns:
      - and:
          - and:
              - and:
                  - jq: '.protocol == "http"'
                  - jq: '.ssl == false'
              - jq: '.auth == "none"'
          - jq: '.exposed == true'
    actions:
      - replace:
          jq: '.protocol = "https" | .ssl = true | .auth = "required" | .exposed = false'
```

**Before:**
```json
{ "protocol": "http", "ssl": false, "auth": "none", "exposed": true, "port": 80 }
```

**After:**
```json
{ "protocol": "https", "ssl": true, "auth": "required", "exposed": false, "port": 80 }
```

The inner `and` checks `protocol` and `ssl`. The middle `and` adds the `auth`
check. The outer `and` adds the `exposed` check. All four must be simultaneously
true before any field is changed.

---

## 19. Three-step nested jq chain

**Scenario:** Enforce a production hostname buried three levels deep in a
config object without knowing the full path upfront.

```yaml
version: 1
rules:
  - id: enforce-production-api-host
    description: Replaces localhost in server.config.host via a 3-step jq chain
    file: /etc/myapp/config.json
    filetype: json
    patterns:
      - nested:
          - jq: '.server'
          - jq: '.config'
          - jq: '.host == "localhost"'
    actions:
      - replace:
          jq: '.server.config.host = "api.production.internal"'
```

**Before:**
```json
{
  "server": {
    "name": "api",
    "config": { "host": "localhost", "port": 3000 }
  }
}
```

**After:**
```json
{
  "server": {
    "name": "api",
    "config": { "host": "api.production.internal", "port": 3000 }
  }
}
```

Each step in a `nested` chain receives the output of the previous step. The
first `jq` extracts the `server` object, the second extracts `config` from
that, and the third checks whether `host` equals `"localhost"`. If the chain
breaks at any step the rule does not fire.

---

## Tips

- **Multiple files.** The `file:` key accepts an array. The same rule applies
  to every path in the list — useful for enforcing the same policy across
  several tools that share a config format.

- **Chain actions.** Actions execute in sequence on the current file state. You
  can `replace` a value and then `request` a notification webhook in the same
  rule.

- **Default content.** Add a `default:` field to a rule to write an initial
  file if it does not yet exist. This ensures patterns always have something to
  evaluate, even on a fresh machine.

- **Dry-run before deploying.** Test any rule locally with:
  ```bash
  warden test -r my-rule.yml -f target-file --dry-run
  ```
