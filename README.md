# Warden

![Warden mascot](docs/assets/images/mascot.png)

> [!WARNING]
> This project is in early stages. Expect bugs, breaking changes, and incomplete documentation. Probably not ready for production use yet. Feedback and contributions are welcome!


Warden is a policy enforcement agent for endpoint configuration files. It
watches specific files for changes and automatically corrects values that
violate your organization's rules — without locking the file away from the user.

Deploy an application, define which settings must stay within policy, and let
Warden silently enforce them. Users keep full control of everything else.

**Common use cases:**

- Remove unapproved MCP servers from AI tool configs (Claude Code, Cursor, VS Code)
- Prevent users from disabling security prompts or permissions
- Enforce recording retention settings in tools like SuperWhisper
- Redact hardcoded secrets from config files as they are saved
- Delete forbidden config files the moment they appear
- Alert your security team via webhook when a policy is violated

---

## Why not existing tools?

There are established tools for policy enforcement and compliance, but none of them are designed for this specific problem:

**MDM configuration profiles** (Jamf, Kandji, Mosyle) can lock files completely — but that removes user agency and often breaks the application. They also only work with predefined Apple preference keys, not arbitrary JSON or YAML application configs.

**OpenSCAP** (Red Hat) scans systems for compliance against security frameworks like CIS and HIPAA. It operates on a schedule and is oriented toward OS-level settings, not application config files. It cannot watch a file in real time and correct a single value.

**osquery** (Meta) provides real-time file integrity monitoring with SQL-like queries. It detects changes, but it is a pure observability tool — it has no ability to remediate. Actual enforcement requires wiring up external automation.

**Ansible** (Red Hat) can enforce file content through scheduled playbook runs, but it is batch-oriented and not continuously watching files. It also cannot surgically correct a single value — it replaces or rewrites lines, which risks breaking file structure. Could be done through custom scripts though but not as practical

Warden is purpose-built for the gap these tools leave: **real-time, surgical enforcement of specific values in application config files, without taking the file away from the user**.
