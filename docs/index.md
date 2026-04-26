# Warden

<p align="center">
  <img src="assets/images/mascot.png" alt="Warden mascot" width="300"/>
</p>

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

---

## Why not existing tools?

There are established tools for policy enforcement and compliance on macOS. None of them are designed for this specific problem.

### MDM configuration profiles

MDM solutions like Jamf, Kandji, and Mosyle can lock files completely by pushing configuration profiles — but that removes user agency and often breaks the application. More critically, configuration profiles only work with predefined Apple preference domains. They have no ability to enforce arbitrary values inside a JSON, YAML, or TOML config file written by a third-party application.

### OpenSCAP (Red Hat)

OpenSCAP is a compliance scanning and remediation tool built around security frameworks like CIS benchmarks and HIPAA. It runs on a schedule, reports what is out of compliance, and can apply remediation scripts. It is designed for OS-level settings and CVE mitigation — not for watching a developer tool's config file and correcting a specific JSON key the moment a user saves it.

### osquery (Meta)

osquery provides real-time file integrity monitoring through SQL-like queries and is widely used for security observability. It can detect the moment a file changes, but it is a pure observability tool — it has no ability to remediate. Enforcement requires wiring osquery events into a separate automation pipeline, adding significant operational complexity for what should be a simple rule.

### Ansible (Red Hat)

Ansible can enforce file content through playbooks using modules like `lineinfile`, but it is fundamentally batch-oriented. It runs on a schedule or when triggered manually — not continuously. A user can change a config value and it stays changed until the next Ansible run. Ansible also cannot surgically correct a single value within a structured file without risk of breaking the surrounding content.

---

### What Warden does differently

Warden is purpose-built for the gap these tools leave. It enforces specific values inside application config files in real time — the moment a file is saved — and corrects only the violating value, leaving everything else the user configured untouched. No scheduler, no pipeline, no full-file replacement (unless intended).
