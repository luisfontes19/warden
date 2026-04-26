# Warden

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

## Documentation

| | |
|---|---|
| [Getting Started](docs/tutorial.md) | Install Warden and write your first rule |
| [Rule Examples](docs/examples.md) | Practical use-case walkthroughs |
| [Rules Reference](docs/rules.md) | Complete pattern and action syntax |
| [MDM Configuration & Bundle Signing](docs/mdm.md) | Deploy rules to your fleet securely |
