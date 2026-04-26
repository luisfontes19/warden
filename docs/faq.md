# FAQ

---

## Why can only admins execute the `warden` binary?

The `warden` binary is installed with `root:admin` ownership and `750` permissions,
meaning only root and members of the `admin` group can run it directly.

This is intentional. Warden runs as **root** (via a LaunchDaemon on macOS)
so that it can enforce policies on files owned by any user.
That elevated privilege is a feature — but it also creates a risk: if an unprivileged
user could invoke the binary, they could exploit it as a living-off-the-land tool to:

- **Read files they should not have access to** — by crafting a rule that matches
  and reports the content of any file on the system (e.g. `/etc/shadow`,
  SSH private keys, other users' home directories).
- **Write or overwrite arbitrary files** — by using `replace` or `add` actions
  against paths the unprivileged user could never open directly.

Restricting execution to admins matches Warden's privilege level to the set of
users already trusted with root-equivalent access on the machine. A regular user
gaining admin rights would be a separate security boundary breach — not something
Warden needs to defend against.
