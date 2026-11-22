# Production signing preparation (no credentials configured)

This document records the exact external credentials required to publish a
**trusted signed** Keel release. None of these values exist in the current
environment; no fake certificate is generated and no unsigned package is
described as signed.

## Windows — Authenticode

- GitHub repository secret: `WINDOWS_SIGNING_CERTIFICATE_BASE64` (PFX, base64)
- GitHub repository secret: `WINDOWS_SIGNING_PASSWORD`
- Timestamping: public RFC 3161 timestamp server (no credential)
- Verification: `signtool verify /pa /v <installer>` after build

## macOS — Developer ID + notarization

- GitHub repository secret: `MACOS_SIGNING_CERTIFICATE_BASE64` (p12, base64)
- GitHub repository secret: `MACOS_SIGNING_PASSWORD`
- GitHub repository secret: `MACOS_NOTARIZATION_APPLE_ID`
- GitHub repository secret: `MACOS_NOTARIZATION_TEAM_ID`
- GitHub repository secret: `MACOS_NOTARIZATION_PASSWORD` (app-specific)
- Verification: `codesign --verify --deep --strict`, `spctl -a -vv`, and
  `xcrun stapler validate` on the notarized DMG.

## Linux — provenance/integrity

No platform-wide trusted signing identity is configured. Required evidence is
the committed SHA-256 manifest, release manifest and signed release tag. If
the owner configures a signing key, the secret must be
`LINUX_SIGNING_KEY_BASE64` with passphrase `LINUX_SIGNING_PASSWORD`.

## Rules

- Signing jobs must be skipped (not failed) when secrets are absent, and the
  release summary must state `unsigned`.
- No release may be published as signed without a successful verification
  step for that platform.
- Secrets are never echoed into logs or artifacts.
