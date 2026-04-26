# Warden Rules — Syntax Reference

Rules are written in YAML files and tell Warden which files to watch, what to
look for, and what to do when a match is found.

---

## 1. File structure

A rules file must have a `rules` key containing a list of rule objects.
An optional `version` integer documents the schema version.

```yaml
version: 1
rules:
  - id: my-first-rule
    file: path/to/watched.txt
    patterns:
      - contains: forbidden
```

Multiple rules files can coexist in the same folder — Warden loads all `*.yml`
files from the configured rules folder.

---

## 2. Rule fields

### 2.1 `id`

**Required.** A unique string that identifies the rule. Used in reports and logs.

```yaml
id: no-debug-statements
```

---

### 2.2 `file`

**Required.** The path(s) to the file(s) this rule inspects. Accepts a single
string or an array of strings. All paths are relative to the working directory
Warden is started from.

Each entry can be a literal path or a **regex pattern**. When matching,
`^` and `$` anchors are added automatically, so the pattern always matches
the full path.

```yaml
# single file
file: config/settings.json

# multiple files — the same patterns and actions apply to each
file:
  - config/settings.json
  - config/settings.local.json

# regex — matches any .json file under config/
file: config/.*\.json
```

---

### 2.3 `description`

**Optional.** A human-readable sentence explaining what the rule detects.
Shown in match reports.

```yaml
description: Detects use of the deprecated API key format
```

---

### 2.4 `filetype`

**Optional.** Forces a specific file parser. When omitted Warden infers the
type from the file extension.

| Value    | Behaviour                                 |
|----------|-------------------------------------------|
| `json`   | Parse as JSON; patterns receive an object |
| `text`   | Read as UTF-8 string (default for unknown extensions) |
| `binary` | Read as raw bytes                         |

```yaml
# Treat a .conf file as plain text
filetype: text

# Treat a .data file as JSON
filetype: json
```

---

### 2.5 `patterns`

**Optional.** A single [pattern node](#3-pattern-nodes) or a list of them.

- A **single node** is evaluated directly.
- A **list** is treated as an implicit **AND** — all nodes must match.

```yaml
# single pattern
patterns:
  - contains: forbidden

# implicit AND — both must match
patterns:
  - contains: TODO
  - match: "FIXME|HACK"
```

When `patterns` is omitted the rule always matches — actions run unconditionally
for the target file(s).

---

### 2.6 `actions`

**Optional.** A list of [action nodes](#4-action-nodes) to apply to the file
when the rule matches.

Actions are executed in order. Each action operates on the current state of the
file on disk — if multiple actions modify the same file they chain.

```yaml
actions:
  - delete:          # remove the matched content
  - add: "\n# cleaned up by Warden\n"
```

> **Text vs JSON:** Text files support `delete`, `replace`, and `add`. JSON
> files only support `replace`.

---

### 2.7 `default`

**Optional.** A string value that is written to the file if it does not exist
when the rule is loaded. The file is created (including parent directories)
before any patterns are evaluated.

This is useful for ensuring a configuration file always exists with known
defaults, so that subsequent patterns and actions can operate on it.

```yaml
rules:
  - id: ensure-config
    file: config/settings.json
    default: '{"debug": false}'
    patterns:
      - jq: '.debug == true'
    actions:
      - replace:
          jq: '.debug = false'
```

> **Warning:** `default` does not work well with regex file paths. Because
> regex paths are resolved dynamically at evaluation time, Warden cannot create
> a file from a regex pattern. If `file` contains a regex, `default` is
> silently ignored for that entry.

---

## 3. Pattern nodes

Every pattern node is a YAML mapping with **exactly one key**.

### 3.1 `contains`

Matches when the content contains the given value.

| Content type | Behaviour |
|--------------|-----------|
| `string`     | Substring check |
| `bytes`      | Byte-substring check |
| `list`/`dict`| Membership check (value must be in the collection) |

`matched_content` is set to the needle value.

```yaml
# text file — checks for a substring
- contains: "TODO"

# JSON file — checks that the string "admin" exists somewhere in the parsed object
- contains: admin
```

---

### 3.2 `not-contains`

Inverse of `contains`. Matches when the value is **not** present.

`matched_content` is the full content (nothing was extracted).

```yaml
# Passes only if the file does NOT mention "debug"
- not-contains: debug
```

---

### 3.3 `equals`

Matches when the content is strictly equal to the value.
Most useful on JSON files after a `jq` extraction step (see [and](#38-and)).

```yaml
# Whole-file equality check on a tiny JSON flag file
- equals: true
```

---

### 3.4 `not-equals`

Inverse of `equals`.

```yaml
- not-equals: "production"
```

---

### 3.5 `match`

Applies a Python `re.search()` regex to the string representation of the
content. Matches when the pattern is found.

`matched_content` is set to the **first matched substring** (a `RegexMatchResult`
that behaves like a string but also carries capture groups — see below).

```yaml
# Detects any 40-character hex string (e.g. a git SHA hardcoded in config)
- match: "[0-9a-f]{40}"

# Detects AWS access key patterns
- match: "AKIA[0-9A-Z]{16}"

# Case-insensitive flag
- match: "(?i)password\\s*="
```

#### Named and positional capture groups

Standard Python regex capture groups work inside `match` patterns and can be
referenced in `replace` action values via `${{…}}` template expressions.

| Variable | Type | Description |
|---|---|---|
| `${{ match }}` | string | Full matched text |
| `${{ groups.name }}` | string | Value of named group `(?P<name>…)` |
| `${{ group[0] }}` | string | Value of the 1st positional group (0-indexed) |
| `${{ group[1] }}` | string | Value of the 2nd positional group, and so on |

```yaml
# Preserve the key, redact only the value using a named group
patterns:
  - match: "(?P<key>\\w+)=(?P<value>[\\d.]+)"
actions:
  - replace: "${{ groups.key }}=REDACTED"
# "version=1.2.3" → "version=REDACTED"

# Same using a positional group
patterns:
  - match: "(\\w+)=([\\d.]+)"
actions:
  - replace: "${{ group[0] }}=REDACTED"
# "version=1.2.3" → "version=REDACTED"
```

> **Note:** Template expressions in `replace` are only evaluated when the
> matched content comes from a `match` pattern. Plain string `replace` values
> work exactly as before for all other pattern types.

---

### 3.6 `jq`

Evaluates a [jq](https://stedolan.github.io/jq/) expression against the parsed
JSON content. Matches when the result is **truthy** (non-null, non-false,
non-empty array/string).

`matched_content` is set to the jq output.

```yaml
# Match if any dependency version starts with "*"
- jq: '[.dependencies | to_entries[] | select(.value | startswith("*"))]'

# Match if the "env" field is not "production"
- jq: '.env != "production"'

# Collect all mcpServer keys that are NOT approved
- jq: |
    [.mcpServers | to_entries[]
      | select((.value.args // []) | contains(["github:anaisbetts/mcp-youtube"]) | not)
      | .key]
```

---

### 3.7 `or`

Matches when **at least one** sub-pattern matches.
`matched_content` is the extracted value from the first sub-pattern that matched.

```yaml
- or:
    - contains: "ERROR"
    - contains: "FATAL"
    - match: "Exception:"
```

---

### 3.8 `and`

Matches when **all** sub-patterns match.
`matched_content` is the extracted value from the **last** sub-pattern (allowing
a pipeline: earlier patterns filter, the final one extracts).

```yaml
# Matches a JSON file that has a "debug" key set to true
- and:
    - jq: 'has("debug")'
    - jq: '.debug == true'
```

A top-level list of patterns is equivalent to a top-level `and`:

```yaml
# These two are identical
patterns:
  - contains: foo
  - contains: bar

patterns:
  - and:
      - contains: foo
      - contains: bar
```

---

### 3.9 `nested`

Chains patterns so that each pattern's match is re-parsed and fed as input to
the next pattern. This is useful when you need to extract a value (e.g. with
`jq`) and then run further checks on that extracted value.

Between each step, the matched content is re-parsed using the same parser as the
file's `filetype` (e.g. JSON files are parsed as JSON). If parsing fails, the
value falls back to a plain string so the chain can continue.

```yaml
# Extract the blocked server's first arg, then check it contains "evil"
patterns:
  - nested:
      - jq: '.servers.blocked.args[0]'
      - contains: evil
```

`matched_content` is the result of the **last** pattern in the chain.

---

### 3.10 `exists`

Matches when the **file itself exists** on disk. Takes no value.
Useful for triggering actions (such as `delete-file`) whenever a watched file
appears.

```yaml
patterns:
  - exists:
```

---

### 3.11 `not-exists`

Inverse of `exists`. Matches when the file does **not** exist on disk.

```yaml
patterns:
  - not-exists:
```

---

## 4. Action nodes

Every action node is a YAML mapping with **exactly one key**.
Actions are applied after all patterns have matched and operate on the file at
`matched.file`.

### 4.1 `delete` (text)

Removes every occurrence of `matched_content` from the file.
The key is present but has no value (`null`).

```yaml
actions:
  - delete:
```

**Before** (`example.txt`):
```
The word pariatur appears here and pariatur appears again.
```

**After** (if `matched_content` is `"pariatur"`):
```
The word  appears here and  appears again.
```

---

### 4.2 `replace` (text)

Replaces every occurrence of `matched_content` with the given string.

```yaml
actions:
  - replace: "[REDACTED]"
```

**Before:**
```
Contact support@internal.corp for help.
```

**After** (if `matched_content` is `"support@internal.corp"`):
```
Contact [REDACTED] for help.
```

---

### 4.3 `add` (text)

Appends the given string to the end of the file. Useful for inserting a
trailing newline or a comment block.

```yaml
actions:
  - add: "\n# Last modified by Warden\n"
```

---

### 4.4 `replace` (JSON)

For JSON files `replace` rewrites the entire file. The value must be one of:

#### `str` — write a literal JSON string as the new file content

```yaml
actions:
  - replace:
      str: '{"env": "production", "debug": false}'
```

#### `jq` — transform the current content with a jq expression

The jq expression receives the current parsed file and its output is written
back as formatted JSON.

```yaml
# Remove all mcpServer entries that are not approved
actions:
  - replace:
      jq: |
        .mcpServers |= with_entries(
          select(.value.args // [] | contains(["github:anaisbetts/mcp-youtube"]))
        )
```

**Before** (`mcp.json`):
```json
{
  "mcpServers": {
    "brave-search": { "command": "npx", "args": ["-y", "@modelcontextprotocol/server-brave-search"] },
    "youtube":      { "command": "npx", "args": ["-y", "github:anaisbetts/mcp-youtube"] }
  }
}
```

**After:**
```json
{
  "mcpServers": {
    "youtube": { "command": "npx", "args": ["-y", "github:anaisbetts/mcp-youtube"] }
  }
}
```

---

### 4.5 `delete-file`

Deletes the matched file from disk. The key is present but has no value (`null`).
No file content is needed — this action works even when paired with `exists` or
`not-exists` patterns.

```yaml
actions:
  - delete-file:
```

---

### 4.6 `code`

Invokes a custom Python handler. The value is a path to a Python file relative
to the rules directory. The file must expose a `handler(filename)` function.
The handler receives the path to the matched file and can read / modify it
freely.

The code path cannot traverse outside the rules directory (path-traversal
attempts raise an error).

> **Security:** Code actions must be explicitly allowed before they can run.
> Set `allow-code-rules` to `true` in your MDM policy, or set the environment
> variable `ALLOW_CODE_RULES=true`. If neither is set, code actions are
> disabled by default.

```yaml
actions:
  - code: my_handler.py
```

Example handler (`my_handler.py`):

```python
def handler(filename):
    with open(filename, encoding="utf-8") as f:
        content = f.read()
    content = content.replace("bad", "good")
    with open(filename, "w", encoding="utf-8") as f:
        f.write(content)
```

---

### 4.7 `request`

Sends an HTTP request. Useful for notifying external systems (webhooks, Slack,
PagerDuty, etc.) when a rule matches.

The value is an object with the following fields:

| Field     | Required | Default | Description |
|-----------|----------|---------|-------------|
| `url`     | **yes**  | —       | The URL to send the request to. |
| `method`  | no       | `POST`  | HTTP method (`GET`, `POST`, `PUT`, `PATCH`, `DELETE`). |
| `headers` | no       | `{}`    | HTTP headers as key-value pairs. |
| `body`    | no       | —       | Request body sent as a string. Supports `${{}}` placeholders. |

All string values support **[placeholders](#5-placeholders)**.

```yaml
actions:
  - request:
      url: https://hooks.slack.com/services/T00/B00/xxx
      method: POST
      headers:
        Content-Type: application/json
      body: '{"text": "Rule ${{rule_id}} triggered on ${{file}}", "matched": "${{matched_content}}"}'
```

---

## 5. Placeholders

Action fields that accept strings can contain **placeholders** using the
`${{…}}` syntax (Jinja2 under the hood). Placeholders are resolved at
execution time with data from the current match.

### 5.1 Available variables

| Variable          | Description |
|-------------------|-------------|
| `rule_id`         | The `id` of the matched rule. |
| `description`     | The rule's `description` field (may be empty). |
| `file`            | The path to the matched file. |
| `file_content`    | The full file content (parsed object for JSON, string for text). |
| `matches`         | List of all `Match` objects. Each has `.rule_id`, `.description`, `.file`, `.matched_content`, `.file_content`. |

### 5.2 Available functions

| Function    | Description |
|-------------|-------------|
| `json(val)` | Serialise any value to a JSON string. Works with `matches`, a single `Match`, or any other value. |

### 5.3 Examples

```yaml
# Simple string interpolation
body: "Alert: ${{rule_id}} found ${{matched_content}} in ${{file}}"

# Access individual matches
body:
  first: "${{matches[0].matched_content}}"
  file: "${{matches[0].file}}"

# Serialise all matches to JSON
body:
  text: "Violations found"
  details: "${{json(matches)}}"

# Inside nested objects
body:
  channel: "#security"
  text: "Violation detected by ${{rule_id}}"
  file: "${{file}}"
```

Placeholders are currently supported in the `request` action. Other actions
may gain placeholder support in the future.

---

## 6. `matched_content`

`matched_content` is the value that pattern evaluation "bubbles up" and is
used by actions as the target to delete/replace. The table below summarises
what each pattern sets it to:

| Pattern      | `matched_content`                              |
|--------------|------------------------------------------------|
| `contains`   | The needle string/bytes/value                  |
| `not-contains` | The full file content (nothing extracted)    |
| `equals`     | The full file content                          |
| `not-equals` | The full file content                          |
| `match`      | The first regex-matched substring              |
| `jq`         | The jq output value                            |
| `or`         | Value from the first branch that matched       |
| `and`/list   | Value from the last sub-pattern that matched   |
| `exists`     | The file path as a string                      |
| `not-exists` | The file path as a string                      |

For complete worked examples with before/after comparisons, see [examples.md](examples.md).
