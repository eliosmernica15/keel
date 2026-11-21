# Changelog

All notable changes to Keel are recorded here. The format follows
"Keep a Changelog"; versions follow semantic versioning.

## [Unreleased]

### Added
- Master Plan v6 and machine-readable feature registry (`PLAN-INDEX.json`,
  `parity.json`) covering both addenda without dropping feature IDs.
- Release hardening: manifest policy fields, mirror failover, staged rollouts,
  release dry-run and a zero-secrets artifact scan.
- Local-first privacy: outbound credential redaction, output DLP, egress log,
  read-only sessions, network egress allowlist and a global kill switch.
- Agent reliability: circuit breaker, doom-loop guard, tolerant tool-call JSON,
  automatic verification, Duet builder/reviewer and memory provenance.
- Product surfaces: per-surface configuration, composer attachments with fuzzy
  `@file` search, opt-in voice dictation and group-chat loop guards.
- Custom Python tools with explicit approval, CLI attach to a running daemon,
  per-vendor cost caps and resumable verified model downloads.

## [0.1.1] - 2026-11-21

### Added
- Windows NSIS installer, macOS Intel and Linux RPM targets.
- Ed25519 artifact signing, signed manifests and verified updates.
- Encrypted provider-key storage with keyring/passphrase fallback.
- Full hook lifecycle coverage across sessions, tools, tasks and elicitation.

## [0.1.0] - initial local build

### Added
- Python-authoritative agent runtime, Electron shell and SQLite persistence.
- Local web bridge, Fleet multi-agent environment and offline provider catalog.
