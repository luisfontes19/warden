# Warden — Bundle Signing Guide

This guide explains how to create **signed rule bundles** — zip archives whose
contents are cryptographically verified by Warden before being loaded.

Signing ensures that only rules produced by your security team are executed on
endpoints, even if the delivery channel (S3 bucket, CDN, internal server) is
compromised.

---

## 1. Overview

A **bundle** is a zip file that contains:

- One or more rule files (`*.yml`)
- Any Python handlers referenced by `code` actions (`*.py`)
- A `signatures.txt` manifest — a JSON file mapping each relative path to its
  Ed25519 signature

The **public key** is distributed separately via MDM policy
(`bundle-signing-public-key`). Warden uses it to verify every file before
loading. Files not present in the manifest, or whose signatures do not match,
are silently rejected.

---

## 2. Signing algorithm

| Property | Value |
|---|---|
| Algorithm | Ed25519 (EdDSA over Curve25519) |
| Signature size | 64 bytes |
| Private key format | DER / PKCS8 (`.ed25519`) |
| Public key format | Raw 32-byte key, base64-encoded in MDM config |

> **Planned upgrade:** The implementation will be migrated to ML-DSA-65
> (CRYSTALS-Dilithium, NIST FIPS 204) once the `cryptography` library's
> bundled OpenSSL exposes the post-quantum provider. The `bundle-signing-public-key`
> MDM field format will change at that point; a migration guide will be provided.

---

## 3. Generating a key pair

Run this once, on the admin machine that will sign bundles:

```bash
warden bundle keygen
```

Output:

```
Private key saved to: /root/.warden/key.ed25519

Public key (add to MDM policy as 'bundle-signing-public-key'):
  <base64-encoded 32-byte public key>

Warning: 'bundle-error-url' is not configured in MDM policy.
Configure it so agents can report bundle verification failures.
```

### Options

| Flag | Description |
|---|---|
| `--output PATH` | Save private key to a custom path instead of `~/.warden/key.ed25519` |
| `--no-save` | Print the public key without writing the private key to disk |

### Key security

- The private key file is written with mode `0o600` (owner-readable only).
- **Never commit or share** the private key. Only the base64 public key is
  distributed.
- Store the private key in a secrets manager (1Password, Vault, etc.) and
  check it out only when signing a new bundle.

---

## 4. Signing a bundle

Given a folder of rule files:

```
my-rules/
  block-debug.yml
  approved-mcps.yml
  cleanup.py
```

Run:

```bash
warden bundle create --rules-folder my-rules/ --output my-rules.zip
```

This will:

1. Sign every file in `my-rules/` (recursively) with your private key at
   `~/.warden/key.ed25519`.
2. Write `my-rules/signatures.txt` — the signature manifest.
3. Zip `my-rules/` (including `signatures.txt`) to `my-rules.zip`.

### Options

| Flag | Description |
|---|---|
| `--rules-folder PATH` | *(required)* Folder containing rule files to sign |
| `--key PATH` | Use a private key at a custom path |
| `--output PATH` | *(required)* Destination zip file |

### Example `signatures.txt`

```json
{
  "version": 1,
  "algorithm": "ed25519",
  "files": {
    "block-debug.yml": "<base64-signature>",
    "approved-mcps.yml": "<base64-signature>",
    "cleanup.py": "<base64-signature>"
  }
}
```

---

## 5. Deploying via MDM

### Step 1 — Host the bundle

Upload `my-rules.zip` to a server your endpoints can reach:

```
https://assets.example.com/warden/my-rules.zip
```

### Step 2 — Configure MDM policy

Add the following fields to your managed policy (see [mdm.md](mdm.md) for
platform-specific syntax):

| Field | Value |
|---|---|
| `rules-url` | URL of the zip file |
| `bundle-signing-public-key` | Base64 public key printed by `warden bundle keygen` |
| `bundle-error-url` | *(recommended)* URL to receive verification failure reports |

**`bundle-signing-public-key` is required when `rules-url` is set.** Warden
will refuse to start if `rules-url` is configured without a signing key.

### macOS example

```xml
<key>rules-url</key>
<string>https://assets.example.com/warden/my-rules.zip</string>
<key>bundle-signing-public-key</key>
<string>MCowBQYDK2VwAyEA...</string>
<key>bundle-error-url</key>
<string>https://alerts.example.com/warden/bundle-error</string>
```

### Linux example

```json
{
  "rules-url": "https://assets.example.com/warden/my-rules.zip",
  "bundle-signing-public-key": "MCowBQYDK2VwAyEA...",
  "bundle-error-url": "https://alerts.example.com/warden/bundle-error"
}
```

---

## 6. How Warden verifies bundles

When `bundle-signing-public-key` is configured in MDM, Warden enforces
signatures on **every folder it loads rules from**:

1. **Look for `signatures.txt`** in the folder.
   - If missing → log an error, POST to `bundle-error-url` (if configured),
     and **load no rules** from that folder.

2. **Verify each `.yml` file** listed in the manifest using the configured
   public key.
   - Files not in the manifest → skipped (not loaded), error reported.
   - Files with an invalid signature → skipped, error reported.
   - Files with a valid signature → loaded normally.

3. **Code handler verification** — when a rule triggers a `code` action, the
   Python file is also verified against the manifest before execution.
   A missing or invalid signature raises an error and prevents execution.

If `bundle-signing-public-key` is **not** configured, Warden loads rule files
without any signature check (existing behaviour, suitable for development).

---

## 7. Error reporting

When signature verification fails, Warden POSTs a JSON payload to
`bundle-error-url`:

```json
{
  "error": "Unverified rule file skipped: bad-rule.yml",
  "source": "warden-bundle-verification"
}
```

This lets your security team receive real-time alerts when an endpoint detects
a tampered bundle. Integrate with Slack, PagerDuty, or a SIEM by pointing the
URL at a webhook or event ingestion endpoint.

> `bundle-error-url` is an MDM-only configuration. The `warden bundle create`
> command will warn you if it is not configured when Warden is running in a
> managed environment.

---

## 8. End-to-end flow

```
Admin machine                          Endpoint (Warden agent)
─────────────────────────────          ───────────────────────────────────────

1. warden bundle keygen
   → key.ed25519 (private)
   → <pub_b64> (public key)

2. Push <pub_b64> to MDM as
   bundle-signing-public-key

3. Edit rules in my-rules/

4. warden bundle create \
       --rules-folder my-rules/ \
       --output my-rules.zip
   → signatures.txt written
   → my-rules.zip created

5. Upload my-rules.zip to
   https://assets.example.com/
   warden/my-rules.zip
                                       6. Warden starts, reads MDM policy:
                                          rules-url → downloads my-rules.zip
                                          bundle-signing-public-key → stored

                                       7. Warden extracts zip, finds
                                          signatures.txt

                                       8. For each .yml file:
                                          verify_file(pub_key, signature)
                                          ✓ valid → load rule
                                          ✗ invalid → skip + POST error

                                       9. For each code: action:
                                          verify_file(pub_key, .py signature)
                                          ✓ valid → execute handler
                                          ✗ invalid → raise error, block exec
```
