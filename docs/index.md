# Warden

Modern software is full of user-editable configuration files. That flexibility is powerful — but from an administrator's perspective, it creates a gap: you can deploy an application, but you cannot guarantee that users will keep it configured the way your organization requires.

**Warden closes that gap.** It is a policy enforcement agent that runs silently on endpoints, watches specific files for changes, and automatically corrects values that violate your rules — without taking control of the file away from the user.

---

## The problem Warden solves

Think about tools like Claude Code or VSCode. Each of them stores its configuration in a file that the user can freely edit:

- A user adds an arbitrary MCP server to their Claude config, connecting their AI assistant to an unapproved third-party service.
- VSCode that doesn't allow administrators to enforce most of the settings.

MDM profiles can lock a config file completely — but that removes user agency and often breaks the tool. Warden takes a different approach: **users keep full control of their settings, and Warden enforces only the values that matter**.

If a user changes a setting Warden is enforcing, Warden detects the change the moment the file is saved and corrects just that value. Everything else the user configured stays intact.

---

## How it works

Warden is driven by **rules** — YAML files that describe:

1. **Which file to watch** — a path, a list of paths, or a regex.
2. **What to look for** — patterns that match text, JSON values, regex, or jq expressions.
3. **What to do when a match is found** — correct the value, delete the entry, recreate the file, or send an alert.

Rules are deployed to endpoints through your MDM solution. Warden picks them up automatically, starts watching the target files, and enforces the policies on every save.
