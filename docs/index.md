# Warden

Warden is a file policy enforcement agent. It monitors files for changes and automatically applies rules — keeping config files, secrets, and tool settings compliant with your organization's policies.

## What it does

- Watches files in real time using filesystem events
- Evaluates rules written in YAML against file contents
- Applies actions (replace, delete, redact, notify) when a rule matches
- Supports MDM-managed policies on macOS and Linux
- Verifies signed rule bundles to prevent tampering

## Quick links

- [Getting Started](tutorial.md) — install Warden and write your first rule
- [Rules Reference](rules.md) — full syntax for patterns and actions
- [Bundle Signing](bundle.md) — sign and deploy rule bundles via MDM
- [MDM Configuration](mdm.md) — platform-specific managed policy reference