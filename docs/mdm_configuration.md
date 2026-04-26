# Warden — MDM Configuration & Bundle Signing

This guide covers managed policy fields and signed bundle delivery.

Installation is covered in [getting_started.md](getting_started.md). This page
starts after Warden is already installed on endpoints.

For the rule syntax itself, see [rules_reference.md](rules_reference.md).

---

## 1. Overview

Warden reads its configuration from a **managed policy** — a file or profile
pushed to endpoints by your MDM solution (Jamf, Kandji, Mosyle, Fleet,
etc.).

There are two ways to deliver rules to endpoints:

| Method | Description |
|---|---|
| **`rules-url`** | Warden downloads a signed zip bundle from a URL you host. Easy to update — push a new zip without redeploying the policy. |
| **`rules` (inline)** | Rules are base64-encoded directly in the policy. No hosting required. Good for a small, stable set of baseline rules. |

You can use both together: inline rules provide a guaranteed baseline, while
remote rules add dynamic policies that can be updated independently.

> [!WARNING]
> Inline rules can only be updated by redeploying the MDM profile.


When using `rules-url`, Warden verifies the bundle's integrity and authenticity before loading any rules.

> [!NOTE]
> Every signed bundle includes a `signatures.json` file generated automatically
> by `warden bundle create`. It contains an Ed25519 signature for each rule file
> in the bundle, plus a **manifest checksum** — a signature over the complete
> list of files.
>
> On the endpoint, Warden verifies this in two passes:
>
> - **Manifest integrity** — the list of files in `signatures.json` must match
>   what is actually in the bundle. If a file has been added or removed since
>   the bundle was signed, verification fails and no rules are loaded.
> - **Per-file integrity** — each rule's content is verified individually
>   against its stored signature. A single byte change in any rule file causes
>   that check to fail.
>
> This uses **public key cryptography** (Ed25519). The private key signs the
> bundle on the admin machine and is never distributed. Only the corresponding
> public key is pushed to endpoints via MDM as `bundle-signing-public-key`.
> Without the private key it is computationally infeasible to produce a valid
> signature, so endpoints can trust that any bundle that passes verification was
> produced by your security team and has not been modified in transit.

---

## 2. Managed policy fields

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
for this field. See [Deploying rules](#4-deploying-rules-to-endpoints) below.

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

Deploy a `.mobileconfig` profile through your MDM solution. You can start from the sample profile in [github.com/luisfontes19/warden/blob/master/packaging/macos/warden.mobileconfig](https://github.com/luisfontes19/warden/blob/master/packaging/macos/warden.mobileconfig).

> [!WARNING]
> Do not deploy that sample profile unchanged. The `PayloadIdentifier` and
> `PayloadUUID` values in a `.mobileconfig` should be unique for your
> organization and profile instance. Reusing the example values can cause
> collisions with other profiles and makes profile management harder.

To generate a new macOS policy file, use the sample as a template:

```bash
cp packaging/macos/warden.mobileconfig my-warden.mobileconfig
```

Then update these fields before uploading it to your MDM:

1. Replace both `PayloadUUID` values with new UUIDs, for example with `uuidgen`.
2. Replace both `PayloadIdentifier` values with identifiers under your own naming scheme, such as `com.example.security.warden` and `com.example.security.warden.settings`.
3. Edit the Warden settings under `mcx_preference_settings` with your `rules-url`, inline `rules`, `refresh-interval`, and any other managed policy fields you need.

Example UUID generation:

```bash
uuidgen
uuidgen
```

Keep the managed preference domain `io.github.luisfontes19.warden` inside
`mcx_preference_settings` unchanged unless the application domain itself
changes.

For installation sequence and package deployment, see
[getting_started.md](getting_started.md).

---

## 4. Deploying rules to endpoints

Rules are distributed as a signed zip bundle that Warden downloads and verifies
on every endpoint. The steps below cover the full flow: write rules, sign them,
host the bundle, and point the MDM policy at it.

### Step 1 — Write your rules

Collect your rule YAML files in a folder. Python handlers for `code` actions
can live in the same folder.

```
my-rules/
  block-debug.yml
  approved-mcps.yml
  cleanup.py          ← Python handler (only if using code actions)
```

> [!NOTE]
> Files whose names begin with `.` (dotfiles such as `.gitignore` or
> `.DS_Store`) are automatically excluded — they are neither signed nor
> included in the zip.

---

### Step 2 — Generate a signing key pair (first time only)

If you do not already have a key pair, generate one on the admin machine that
will build bundles:

```bash
warden bundle keygen
```

Output:

```
Private key saved to: /root/.warden/key.ed25519
Public key saved to:  /root/.warden/key.ed25519.pub

Public key (add to MDM policy as 'bundle-signing-public-key'):
  <base64-encoded public key>
```

Copy the base64 public key value and set it as `bundle-signing-public-key` in
your MDM policy. This is the only key value that ever leaves the admin machine.

**Key security:**

- The private key is written with mode `0o600` (owner-readable only).
Options:

---

### Step 3 — Create the bundle

Run `bundle create` from the admin machine to sign and package the rules:

```bash
warden bundle create --rules-folder my-rules/ --output my-rules.zip
```

This signs each file with the private key, writes a `signatures.json` manifest,
and produces `my-rules.zip` ready to host.

Options:

| Flag | Description |
|---|---|
| `--rules-folder PATH` | *(required)* Folder containing rules to sign |
| `--output PATH` | *(required)* Destination zip file |
| `--key PATH` | Private key path (default: `~/.warden/key.ed25519`) |

---

### Step 4 — Host the bundle

Upload `my-rules.zip` to any HTTPS server your endpoints can reach, then set
`rules-url` in the MDM policy to the download URL:

```
https://assets.example.com/warden/my-rules.zip
```

Warden downloads and verifies the bundle on startup, and again on every
`refresh-interval` cycle. To push a rule change, rebuild the bundle, upload the
new zip to the same URL, and Warden picks it up on the next refresh — no MDM
profile redeploy needed.

---

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
