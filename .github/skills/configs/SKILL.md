---
name: configs
description: Skill to be used everytime you have to change configs
---

# Instructions

1. Understand if a managed config is also necessary (ask the user if they want to use managed policies or just local rules). Managed configs are configs managed by an MDM solution, through policies
2. If a managed config is needed, add it to `src/warden/managed_policies/base.py`. Make sure the `linux.py` and `macos.py` handlers are updated to support the new config. (if a `windows.py` exists update it as well)
3. Make sure to update the configs to use this setting. Managed configs cannot be overriten. So the sequence should be: environment vars -> user cli params -> managed policies. This means that if a setting is defined in the managed policy, it should override any other setting defined in environment vars or cli params.
4. Update the documentation in `docs/mdm.md` to reflect the new config and how it can be used.
