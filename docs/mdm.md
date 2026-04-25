# Warden — MDM Management Guide

This guide covers how to configure and manage Warden across your organization
using managed policies (MDM).

For the rule syntax itself, see [rules.md](rules.md).

---

## 1. Overview

Warden can be centrally configured through **managed policies**. This allows an
organization to push rules and settings to all endpoints without requiring
manual configuration on each machine.

The policy tells Warden:
- **Where** to fetch rules from (a URL to a zip file, inline base64 rules, or both).
- **Whether** Python-based code rules are allowed.
- **How often** to pull updated rules.

---

## 2. Installation & deployment

<!-- TODO: Document installation and deployment steps -->

---

## 3. Configuration parameters

### 3.1 `rules-url`

| | |
|---|---|
| **Type** | `string` |
| **Required** | No |
| **Default** | *none* |

A publicly accessible URL pointing to a **zip file** containing rule files
(`.yml`). The zip can contain nested directories for organization — Warden will
extract and load all `.yml` files found inside.

Warden downloads and extracts the zip into a local directory, replacing any
previously downloaded rules on each fetch.

```
https://example.com/warden-rules/latest.zip
```

### 3.2 `rules` (inline rules)

| | |
|---|---|
| **Type** | `array of strings` |
| **Required** | No |
| **Default** | *none* |

An array where **each entry is the full content of a rule YAML file, base64-encoded**.

This is useful for shipping a set of default rules directly in the managed
policy without needing to host a zip file. Warden decodes each entry and writes
it as a `.yml` file into the policy rules directory.

**Example — encoding a rule:**

Given a rule file:

```yaml
version: 1
rules:
  - id: block-debug
    file: "**/*.json"
    patterns:
      - contains: "DEBUG"
    actions:
      - delete: "DEBUG"
```

Base64-encode its content:

```bash
base64 < rule.yml
```

Then add the resulting string as an entry in the `rules` array in your managed
policy.

### 3.3 `allow-code-rules`

| | |
|---|---|
| **Type** | `boolean` |
| **Required** | No |
| **Default** | `false` |

Controls whether rules are permitted to use the `code` action keyword to execute
arbitrary Python scripts. When set to `false` (the default), any rule containing
a `code` action is ignored.

> **Security note:** Only enable this if you fully trust the rules being
> delivered to the endpoint. Code rules can execute arbitrary Python with the
> same permissions as the Warden process.

### 3.4 `refresh-interval`

| | |
|---|---|
| **Type** | `integer` (minutes) |
| **Required** | No |
| **Default** | `0` (disabled) |

The interval, in **minutes**, at which Warden re-downloads rules from
`rules-url`. When set to `0` or omitted, Warden only fetches rules once at
startup.

### 3.5 `bundle-signing-public-key`

| | |
|---|---|
| **Type** | `string` (base64-encoded Ed25519 public key) |
| **Required** | Yes, when `rules-url` is set |
| **Default** | *none* |

The Ed25519 public key used to verify signed rule bundles, encoded as base64.
Warden will refuse to start if `rules-url` is configured without this key.

Generate a key pair with `warden bundle keygen` — the public key is printed to
stdout in the correct format. See [bundle.md](bundle.md) for the full signing
workflow.

### 3.6 `bundle-error-url`

| | |
|---|---|
| **Type** | `string` (URL) |
| **Required** | No |
| **Default** | *none* |

A URL that receives a POST request whenever bundle signature verification fails.
Use this to alert your security team when an endpoint detects a tampered or
unsigned bundle. The payload is:

```json
{
  "error": "<description of the failure>",
  "source": "warden-bundle-verification"
}
```

Point this at a Slack webhook, PagerDuty event endpoint, or any SIEM ingest URL.

---

## 4. macOS — Managed profile (.mobileconfig)

On macOS, Warden reads managed preferences from:

```
/Library/Managed Preferences/com.thesecurityvault.warden.plist
```

This plist is populated by deploying a `.mobileconfig` profile through your MDM
solution (Jamf, Kandji, Mosyle, Fleet, etc.).

A reference profile is available at [`Warden.mobileconfig`](Warden.mobileconfig).

### Minimal example

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>PayloadContent</key>
  <array>
    <dict>
      <key>PayloadContent</key>
      <dict>
        <key>com.thesecurityvault.warden</key>
        <dict>
          <key>Forced</key>
          <array>
            <dict>
              <key>mcx_preference_settings</key>
              <dict>
                <key>rules-url</key>
                <string>https://example.com/rules.zip</string>
                <key>rules</key>
                <array>
                  <string>BASE64_ENCODED_RULE_HERE</string>
                </array>
                <key>allow-code-rules</key>
                <false/>
                <key>refresh-interval</key>
                <integer>30</integer>
                <key>bundle-signing-public-key</key>
                <string>BASE64_PUBLIC_KEY_HERE</string>
                <key>bundle-error-url</key>
                <string>https://alerts.example.com/warden/bundle-error</string>
              </dict>
            </dict>
          </array>
        </dict>
      </dict>
      <key>PayloadType</key>
      <string>com.apple.ManagedClient.preferences</string>
      <key>PayloadIdentifier</key>
      <string>com.thesecurityvault.warden.settings</string>
      <key>PayloadUUID</key>
      <string>571D05E1-9E09-4121-A79F-9406E0518CBC</string>
      <key>PayloadVersion</key>
      <integer>1</integer>
    </dict>
  </array>
  <key>PayloadDisplayName</key>
  <string>Warden</string>
  <key>PayloadIdentifier</key>
  <string>com.thesecurityvault.warden</string>
  <key>PayloadScope</key>
  <string>System</string>
  <key>PayloadType</key>
  <string>Configuration</string>
  <key>PayloadUUID</key>
  <string>3CC58BF0-C49D-4F33-9DEB-C032A93EC786</string>
  <key>PayloadVersion</key>
  <integer>1</integer>
  <key>TargetDeviceType</key>
  <integer>5</integer>
</dict>
</plist>
```

---

## 5. Linux — Policy file

On Linux, Warden reads the policy from a JSON file at:

```
/etc/warden/policy.json
```

### Example

```json
{
  "rules-url": "https://example.com/rules.zip",
  "rules": [
    "BASE64_ENCODED_RULE_HERE"
  ],
  "allow-code-rules": false,
  "refresh-interval": 30,
  "bundle-signing-public-key": "BASE64_PUBLIC_KEY_HERE",
  "bundle-error-url": "https://alerts.example.com/warden/bundle-error"
}
```

Deploy this file through your configuration management tool (Ansible, Puppet,
Chef, etc.) or any MDM that supports Linux.

---

## 6. Rules delivery strategies

You can combine `rules-url` and inline `rules` to suit your needs:

| Strategy | `rules-url` | `rules` (inline) | Use case |
|---|---|---|---|
| **Remote only** | Set | Empty | All rules managed in a central repo, downloaded as a zip. Easy to update without redeploying the profile. |
| **Inline only** | Empty | Populated | Rules baked into the managed policy. No external hosting needed. Good for a small, stable set of default rules. |
| **Hybrid** | Set | Populated | Inline rules provide a baseline that is always present. Remote rules add or override for more dynamic policies. |

> **Tip:** Inline rules are extracted on every Warden startup. Remote rules are
> fetched at startup and then again every `refresh-interval` minutes (if set).
