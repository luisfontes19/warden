# Warden Rules — Syntax Reference

Rules are written in YAML files and tell Warden which files to watch, what to
look for, and what to do when a match is found.

---

## Table of Contents

1. [File structure](#1-file-structure)
2. [Rule fields](#2-rule-fields)
   2.1 [id](#21-id)
   2.2 [file](#22-file)
   2.3 [description](#23-description)
   2.4 [filetype](#24-filetype)
   2.5 [patterns](#25-patterns)
   2.6 [actions](#26-actions)
3. [Pattern nodes](#3-pattern-nodes)
   3.1 [contains](#31-contains)
   3.2 [not-contains](#32-not-contains)
   3.3 [equals](#33-equals)
   3.4 [not-equals](#34-not-equals)
   3.5 [match](#35-match)
   3.6 [jq](#36-jq)
   3.7 [or](#37-or)
   3.8 [and](#38-and)
   3.9 [exists](#39-exists)
   3.10 [not-exists](#310-not-exists)
4. [Action nodes](#4-action-nodes)
   4.1 [delete (text)](#41-delete-text)
   4.2 [replace (text)](#42-replace-text)
   4.3 [add (text)](#43-add-text)
   4.4 [replace (JSON)](#44-replace-json)
   4.5 [delete-file](#45-delete-file)
5. [matched_content](#5-matched_content)
6. [Complete examples](#6-complete-examples)

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

```yaml
# single file
file: config/settings.json

# multiple files — the same patterns and actions apply to each
file:
  - config/settings.json
  - config/settings.local.json
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

When `patterns` is omitted the rule never matches.

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

`matched_content` is set to the **first matched substring**.

```yaml
# Detects any 40-character hex string (e.g. a git SHA hardcoded in config)
- match: "[0-9a-f]{40}"

# Detects AWS access key patterns
- match: "AKIA[0-9A-Z]{16}"

# Case-insensitive flag
- match: "(?i)password\\s*="
```

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

### 3.9 `exists`

Matches when the **file itself exists** on disk. Takes no value.
Useful for triggering actions (such as `delete-file`) whenever a watched file
appears.

```yaml
patterns:
  - exists:
```

---

### 3.10 `not-exists`

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

## 5. `matched_content`

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

---

## 6. Complete examples

### Detect and remove a blacklisted word in a text file

```yaml
version: 1
rules:
  - id: remove-blacklisted-words
    description: Removes the word "pariatur" from text files
    file:
      - docs/draft.txt
      - notes/ideas.txt
    filetype: text
    patterns:
      - or:
          - contains: pariatur
          - contains: mollit
    actions:
      - delete:
```

---

### Flag hardcoded secrets in any config file

```yaml
version: 1
rules:
  - id: no-hardcoded-secrets
    description: Detects AWS-style access keys
    file: config/app.env
    filetype: text
    patterns:
      - match: "AKIA[0-9A-Z]{16}"
    actions:
      - replace: "REDACTED_AWS_KEY"
```

---

### Enforce only approved MCP servers (JSON)

```yaml
version: 1
rules:
  - id: approved-mcp-servers-only
    description: Reports and removes any mcpServer that is not the approved youtube one
    file:
      - .cursor/mcp.json
      - .vscode/mcp.json
    filetype: json
    patterns:
      - jq: |
          [.mcpServers | to_entries[]
            | select((.value.args // []) | contains(["github:anaisbetts/mcp-youtube"]) | not)
            | .key]
    actions:
      - replace:
          jq: |
            .mcpServers |= with_entries(
              select(.value.args // [] | contains(["github:anaisbetts/mcp-youtube"]))
            )
```

---

### Require a minimum node version in package.json

```yaml
version: 1
rules:
  - id: node-version-check
    description: Fails if engines.node is not set to >=20
    file: package.json
    filetype: json
    patterns:
      - jq: '.engines.node != ">=20"'
    actions:
      - replace:
          jq: '.engines.node = ">=20"'
```

---

### Chain patterns — extract then validate

Using a list (implicit `and`) to first filter with jq and then assert the result:

```yaml
version: 1
rules:
  - id: production-env-required
    description: Fails when the env field is missing or not "production"
    file: config/deploy.json
    filetype: json
    patterns:
      - jq: 'has("env")'          # must have the key
      - jq: '.env != "production"' # and it must NOT already be production
    actions:
      - replace:
          jq: '.env = "production"'
```

---

### Delete a forbidden config file on sight

```yaml
version: 1
rules:
  - id: remove-forbidden-mcp-config
    description: Deletes any MCP config file as soon as it appears
    file: .cursor/mcp.json
    patterns:
      - exists:
    actions:
      - delete-file:
```
