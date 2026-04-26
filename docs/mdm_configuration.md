# Warden — MDM Configuration & Bundle Signing

This guide covers everything an administrator needs to deploy Warden to a fleet:
configuring the managed policy, creating signed rule bundles, and deploying them
securely.

For the rule syntax itself, see [rules_reference.md](rules_reference.md).

---

## 1. Overview

### Deployment flow

Deploying Warden to a managed fleet requires two sequential MDM pushes:

```
1. Package push   →  installs the binary + LaunchDaemon, starts the service
2. Profile push   →  delivers the managed policy (rules URL, signing key, etc.)
```

Both assets are available on the
[GitHub Releases page](https://github.com/luisfontes19/warden/releases):

---

Warden reads its configuration from a **managed policy** — a file or profile
pushed to endpoints by your MDM solution (Jamf, Kandji, Mosyle, Fleet, Ansible,
etc.). The policy tells Warden where to fetch rules, which security features to
enable, and how often to refresh.

There are two ways to deliver rules to endpoints:

| Method | Description |
|---|---|
| **`rules-url`** | Warden downloads a signed zip bundle from a URL you host. Easy to update — push a new zip without redeploying the policy. |
| **`rules` (inline)** | Rules are base64-encoded directly in the policy. No hosting required. Good for a small, stable set of baseline rules. |

You can use both together: inline rules provide a guaranteed baseline, while
remote rules add dynamic policies that can be updated independently.

---

## 2. Configuration parameters

### `rules-url`

| | |
|---|---|
| **Type** | `string` (URL) |
| **Required** | No |

A URL pointing to a **zip file** containing signed rule files. Warden downloads
and extracts the zip on startup, replacing any previously downloaded rules.
If `bundle-signing-public-key` is set, the bundle must pass signature
verification before any rules are loaded.

```
https://assets.example.com/warden/rules-latest.zip
```

### `rules-url-headers`

| | |
|---|---|
| **Type** | `object` (key-value string pairs) |
| **Required** | No |

Additional HTTP headers sent with every request to `rules-url`. Use this when
the bundle server requires authentication or other request metadata.

### `rules` (inline rules)

| | |
|---|---|
| **Type** | `array of strings` |
| **Required** | No |

An array where **each entry is the full content of a rule YAML file, base64-encoded**.
Inline rules are decoded on every Warden startup and loaded directly — no
signature verification applies to them, since they are part of the managed
policy itself and therefore already under MDM control.

To encode a rule file:

```bash
base64 < my-rule.yml
```

Paste the resulting string as an entry in the `rules` array.

### `allow-code-rules`

| | |
|---|---|
| **Type** | `boolean` |
| **Required** | No |
| **Default** | `false` |

Controls whether rules may use the `code` action to execute Python scripts on
the endpoint. Disabled by default. Only enable this if you fully trust the
rules being delivered — code rules run with the same permissions as the Warden
process.

When `rules-url` is in use, any Python handler referenced by a `code` action is
also verified against the bundle signature before execution. A missing or
tampered handler is blocked regardless of this setting.

### `refresh-interval`

| | |
|---|---|
| **Type** | `integer` (minutes) |
| **Required** | No |
| **Default** | `0` (disabled) |

How often, in minutes, Warden re-downloads rules from `rules-url`. When `0` or
omitted, Warden fetches rules once at startup. Set to `30` or `60` to get
near-real-time policy updates without redeploying the MDM profile.

### `bundle-signing-public-key`

| | |
|---|---|
| **Type** | `string` (base64-encoded Ed25519 public key) |
| **Required** | Required when `rules-url` is set |

The public key used to verify signed rule bundles. Generate a key pair with
`warden bundle keygen` — the output prints the public key in the correct format
for this field. See [Signing workflow](#4-bundle-signing-workflow) below.

When set, Warden verifies the bundle before loading any rules:

1. Checks the bundle's **manifest checksum** — an Ed25519 signature over the
   entire file list, proving the manifest itself has not been tampered with.
2. Verifies the **signature of each rule file** individually.
3. Verifies the **signature of any Python handler** before executing it.

If any verification step fails, Warden loads no rules from that bundle and
reports the failure to `bundle-error-url` (if configured).

> Warden will refuse to start if `rules-url` is set without a
> `bundle-signing-public-key`.

### `bundle-error-url`

| | |
|---|---|
| **Type** | `string` (URL) |
| **Required** | No |

A URL that receives a POST request whenever bundle verification fails on an
endpoint. Use this to alert your security team in real time when a tampered or
unsigned bundle is detected.

The POST body is:

```json
{
  "error": "<description of the specific failure>",
  "source": "warden-bundle-verification"
}
```

Point this at a Slack webhook, PagerDuty event endpoint, or any SIEM ingest URL.
Each failure produces a separate POST with a specific error message (missing
file, invalid signature, etc.).

---

## 3. Platform configuration

### macOS — Managed profile

On macOS, Warden reads managed preferences from:

```
/Library/Managed Preferences/io.github.luisfontes19.warden.plist
```

Deploy a `.mobileconfig` profile through your MDM solution. You can find a sample profile in `packaging/macos/warden.mobileconfig`. Check [mdm](mdm_configuration.md) for instructions on how to edit and deploy it.

Deploy this file through your configuration management tool (Ansible, Puppet,
Chef, etc.) or any MDM that supports Linux file management.

---

## 4. Bundle signing workflow

Signing a bundle cryptographically proves that the rules on an endpoint came
from your security team and have not been modified in transit or on the
delivery server.

Warden uses **Ed25519** signatures. The private key stays on the admin machine
that builds bundles; only the public key is distributed via MDM.

### Step 1 — Generate a key pair (once)

Run this on the admin machine that will sign bundles:

```bash
warden bundle keygen
```

Output:

```
Private key saved to: /root/.warden/key.ed25519
Public key saved to:  /root/.warden/key.ed25519.pub

Public key (add to MDM policy as 'bundle-signing-public-key'):
  <base64-encoded public key>

Warning: 'bundle-error-url' is not configured in MDM policy.
Configure it so agents can report bundle verification failures.
```

**Key security:**

- The private key is written with mode `0o600` (owner-readable only).
- **Never commit or share** the private key. Store it in a secrets manager
  (1Password, Vault, etc.) and check it out only when signing a new bundle.
- Only the base64 public key value is added to the MDM policy.

Options:

| Flag | Description |
|---|---|
| `--output PATH` | Save the private key to a custom path |
| `--no-save` | Print the public key without writing the private key to disk |

### Step 2 — Build and sign a bundle

Organise your rules in a folder:

```
my-rules/
  block-debug.yml
  approved-mcps.yml
  cleanup.py          ← Python handler (if using code actions)
```

> **Note:** Files whose names begin with `.` (dotfiles such as `.gitignore` or
> `.DS_Store`) are automatically excluded from the bundle — they are neither
> signed nor included in the zip archive.

Run:

```bash
warden bundle create --rules-folder my-rules/ --output my-rules.zip
```

This:

1. Signs every non-dotfile in `my-rules/` with your private key.
2. Computes a **manifest checksum** — an Ed25519 signature over the entire file
   list — and writes it to `my-rules/signatures.json`.
3. Zips `my-rules/` (including `signatures.json`) to `my-rules.zip`.

Options:

| Flag | Description |
|---|---|
| `--rules-folder PATH` | *(required)* Folder containing rules to sign |
| `--key PATH` | Use a private key at a custom path (default: `~/.warden/key.ed25519`) |
| `--output PATH` | *(required)* Destination zip file |

### Step 3 — Host the bundle

Upload `my-rules.zip` to any HTTP server your endpoints can reach:

```
https://assets.example.com/warden/my-rules.zip
```

Set `rules-url` in the MDM policy to this URL. That's all — Warden downloads
and verifies the bundle automatically on startup (and on every
`refresh-interval` cycle if set).

### How verification works on the endpoint

When Warden downloads and extracts a bundle, it verifies it in this order:

1. **Manifest checksum** — verifies the Ed25519 signature over the complete
   file list in `signatures.json`. If this fails, the entire bundle is rejected
   immediately and an error is reported.
2. **Per-file signatures** — each rule file (`.yml`) and Python handler (`.py`)
   listed in the manifest is verified individually. Files with an invalid
   signature are skipped; valid ones are loaded.
3. **Missing files** — if a file listed in the manifest is absent from the
   extracted bundle, it is reported as an error.

Any failure triggers a POST to `bundle-error-url` with a specific error
message identifying exactly what went wrong.

### End-to-end flow

```
Admin machine                          Endpoint (Warden agent)
─────────────────────────────          ────────────────────────────────────────

1. warden bundle keygen
   → key.ed25519 (private)
   → <pub_b64> (public key)

2. Add <pub_b64> to MDM policy
   as bundle-signing-public-key

3. Edit rules in my-rules/

4. warden bundle create \
       --rules-folder my-rules/ \
       --output my-rules.zip
   → signatures.json written
   → my-rules.zip created

5. Upload my-rules.zip to
   https://assets.example.com/
   warden/my-rules.zip
                                        6. Warden starts, reads MDM policy:
                                           rules-url → downloads my-rules.zip
                                           bundle-signing-public-key → stored

                                        7. Warden extracts zip, loads
                                           signatures.json

                                        8. Verifies manifest checksum
                                           ✓ valid → proceed
                                           ✗ invalid → reject bundle + report

                                        9. For each .yml rule file:
                                           verify signature
                                           ✓ valid → load rule
                                           ✗ invalid/missing → skip + report

                                       10. For each code: handler (if triggered):
                                           verify .py signature
                                           ✓ valid → execute
                                           ✗ invalid → block + report
```

---

## 5. Rules delivery strategies

| Strategy | `rules-url` | `rules` (inline) | When to use |
|---|---|---|---|
| **Remote only** | Set | Empty | Rules managed in a central repo, downloaded as a zip. Update policies without redeploying the MDM profile. |
| **Inline only** | Empty | Populated | Rules baked into the managed policy. No hosting required. Good for a small, stable set. |
| **Hybrid** | Set | Populated | Inline rules provide a guaranteed baseline. Remote rules add dynamic policies. The two sets are merged. |

> Inline rules are loaded on every Warden startup. Remote rules are fetched at
> startup and again every `refresh-interval` minutes if set. Inline rules do
> not require signing — they are part of the MDM policy itself.
