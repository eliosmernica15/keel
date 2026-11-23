# FREE-TIER-REGISTER.md

Compliance register for every service, dependency, model, voice, font and tool mentioned or
considered across the eight Keel plan documents (Master Plan v5, Addenda 1-7). Required by
Addendum 3 **X0.6** and cross-referenced by Addendum 4. Companion machine-readable registry:
`MODEL-AND-VOICE-LICENSES.json` (X0.7).

This register is a living document. X0.6 requires terms to be **re-verified at each gate**,
especially gate G6 (any decision to pay/monetise).

## Non-negotiable declarations

1. **NO service may become a required paid dependency.** No paid third-party service appears
   anywhere in the plan as mandatory.
2. **All external providers are optional adapters** for services the user already has. They are
   never required, never bundled, never defaulted on, and are enabled only with a user-supplied
   key/endpoint and explicit consent (Master Plan §0.5, §7.6).
3. **Keel boots and works offline with a local model**: it completes a coding task with no
   network, no account and no API key, using Ollama/llama.cpp or another local model
   (Master Plan §0.5; CI-enforced; X0.8 zero-network smoke job).
4. Nothing here grants permission to send user code or private data to a Keel-operated server.

## Evidence source ID legend

| ID | Meaning |
| --- | --- |
| `X0.6` / `X0.7` | Addendum 3 gap rows (free-tier register / license registry) |
| `C11.1`, `C11.2` | Addendum 2 source-hosting caveats / repo hygiene |
| `MPv5 §0.4`, `§0.5`, `§5.2`, `§5.3`, `§7.6`, `§8` | Keel Master Plan v5 requirement blocks in `base-verification.json` |
| `A-x`, `B-x`, `Y-x`, `W-x` | Addendum 1/2/4/5/7 feature rows where a dependency is named |
| `base` | `base-verification.json` requirement/feature rows (shared across plans) |

**Date verified convention:** the date in the table is when this register entry was compiled
from the plan metadata. It is **not** an independent live check of the provider's current terms,
except where a live observation is explicitly noted (the GitHub branch-protection 403). Live
terms must be re-verified at each gate per X0.6.

## Register

| Service/Dependency | Free tier used? | Commercial-use restrictions | Date verified | Licensing obligations | Data & privacy implications | Exit strategy | Optional? (yes/no) | Evidence source ID |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GitHub (source hosting, free private repo) | Yes — private repo on free plan | Free private repos exist but are limited; advanced code/secret scanning and Pages-for-private may require paid. Re-verify current terms. | 2026-11-23 (doc-level) | Hosting ToS only; no licence grant over Keel source | Private source required; no public internal docs/research/plans; no public issue tracker; gitleaks + signed commits; gate G1 visibility | Move primary repo to GitLab free / self-hosted Forgejo/Gitea / Codeberg and mirror; or consciously pay at G6 | yes (project host; end users never touch GitHub) | X0.6; C11.1; MPv5 §0.4 |
| GitHub branch protection / advanced scanning (free-plan gap) | No — unavailable on free; compensated locally | Branch protection unavailable on free private repos — **live check returned 403**; re-verify at gate | 2026-11-23 (live 403 observed) | n/a | Use local pre-push hooks + gitleaks + signed commits; mandatory 2FA, least-privilege tokens, forks disabled, SHA-pinned Actions | Host on a free forge with protected branches (GitLab free / Forgejo/Gitea) and mirror to GitHub; or pay at G6 | yes | X0.6; C11.1 |
| GitHub Actions (private repo CI) | Yes — CI on private repo | Free private-repo minutes are limited; macOS/Windows runners use multiplied minutes; verify current numbers | 2026-11-23 (doc-level) | Runner/Actions ToS; pin actions by commit SHA (C11.2) | CI secrets remain in the private repo; no source archives, private credentials or CI secrets leave it | Heavy matrix only on release tags; caching; optional free self-hosted runners on owner machines; alternative forge CI | yes | X0.6; C11.1; C11.2; MPv5 §8 |
| GitHub Pages (private repo) | Conditional — may need paid | Private-repo Pages may require a paid plan; re-verify | 2026-11-23 (doc-level) | Hosting ToS | Only public binaries/marketing content; never source, docs or keys | Use public binaries-only repo static host (Codeberg/SourceForge/self-hosted) | yes | C11.1; MPv5 §5.3 D5 |
| Vercel Hobby (static website) | Yes (dev/staging) | **Hobby tier is non-commercial** — must migrate before charging anyone | 2026-11-23 (doc-level) | Platform ToS | Static public site only: product info, screenshots, download links, docs. No user code, keys, private docs or internal artifacts; domain rewrites to binaries-only repo | Migrate site to public binaries-only repo (`keel-releases`) static hosting: GitHub Pages, Codeberg, SourceForge or self-hosted static server — before any monetisation | yes | X0.6; MPv5 §0.4, §5.3 D5, §8 |
| VirusTotal public API | Considered only | **Public API is non-commercial** and rate-limited; API key required; verify current terms | 2026-11-23 (doc-level) | API ToS | Submitting samples/hashes to a third party may expose user code or secrets; never send user code; local gitleaks/OSV is the default; explicit user consent only | Remove adapter; rely on local gitleaks + OSV/pip-audit + SBOM/license report | yes | X0.6 |
| Docker Desktop | No — explicitly not required | **Commercial terms**; commercial use requires a paid licence | 2026-11-23 (doc-level) | Docker Desktop subscription terms | Local optional container sandbox only; no user data leaves; prefer engine-only to avoid Desktop telemetry/licence checks | Use Podman / Docker Engine (no Desktop GUI licence); container sandbox is itself optional | yes | X0.6; MPv5 §5.2, §8 |
| Podman / Docker Engine | Yes (optional sandbox) | Engine licences are permissive; verify exact version at gate | 2026-11-23 (doc-level) | Apache-2.0-style engine licences (verify) | Local, outbound-only sandbox; never required | Disable the optional container sandbox entirely | yes | MPv5 §8; base (process model) |
| Alternative free forges / static hosts (GitLab free, Forgejo, Gitea, Codeberg, SourceForge, self-hosted) | Considered as exit hosts | Free tiers generally permit proprietary freeware; re-verify per host, especially public-manifest requirements (Flathub/AUR rules) | 2026-11-23 (doc-level) | Host ToS | No source exposure; only approved binaries/manifests published | Already the exit path — switch host; AUR binary and self-hosted APT/YUM remain | yes | X0.5; C11.1; MPv5 §5.3 D5 |
| Code signing (SignPath Foundation, Apple Developer ID / notarisation) | No — unavailable free | SignPath Foundation unavailable for proprietary software; Apple notarisation needs a paid membership | 2026-11-23 (doc-level) | n/a (no free grant) | Ship unsigned with documented first-run/verification steps; SHA-256 + Ed25519 manifest signatures | Documented SmartScreen steps, right-click Open / `xattr`, winget/Scoop/Homebrew tap, signed APT/RPM; revisit only if owner accepts paid options | yes | MPv5 §5.3 D3; base (free-first rules) |
| ntfy-style push notifications | Yes (optional; self-hosted or public instance chosen by user) | Self-host free; public instances have their own ToS/rate limits — verify | 2026-11-23 (doc-level) | Service ToS (self-host avoids third party) | Notification content leaves the machine; keep payloads minimal/redacted; user chooses endpoint; quiet hours/digests/per-channel routing | Disable notifications or point at a local/self-hosted instance | yes | base (notification rules, M17/M25) |
| Ollama / llama.cpp + local models | Yes — default offline path | No service restrictions locally; **model weights carry their own licences** (see JSON registry) | 2026-11-23 (doc-level) | Engine licence + per-model weights licence; verify before bundling any model | Fully local; no account/key/network; Wizard detects existing models and shows disk/RAM cost before pulling | User supplies any local model; swap engine; no fallback that becomes a paid dependency | no (a local model is the offline-boot path; the engine itself is replaceable) | MPv5 §0.5, §8; A4 (wizard); base |
| OpenAI-compatible local/custom endpoints | Yes — first-class custom endpoint path | Local/LAN servers only by default; no hosted dependency | 2026-11-23 (doc-level) | Server/endpoint terms are the user's own | Data goes only to the endpoint the user configures | Disable custom endpoints; local Ollama/llama.cpp remains | yes | A6 (provider type); MPv5 §8 |
| whisper.cpp (local STT engine) | Yes (voice features) | Engine licence permissive (verify); **weights licence separate** | 2026-11-23 (doc-level) | Engine licence + model-weights licence (see JSON) | Audio processed locally; no upload | Alternative local STT or user-supplied engine; voice features degrade gracefully | yes | X0.7; MPv5 §8; base |
| Piper (local TTS voices) | Yes (voice features) | **Version-dependent licence — license changed between versions**; verify actual version | 2026-11-23 (doc-level; MUST VERIFY) | See JSON entry `piper-tts`; do not bundle until verified | Synthesis local; no upload | Substitute another locally licensed voice or user-supplied voices | yes | X0.7; MPv5 §8 |
| Kokoro voices | Yes (voice features) | **Licence not pinned in plan metadata**; verify before bundling | 2026-11-23 (doc-level; MUST VERIFY) | See JSON entry `kokoro-voices`; do not bundle until verified | Synthesis local; no upload | Substitute another locally licensed voice | yes | X0.7; MPv5 §8 |
| Whisper model weights | Yes (STT weights) | **Weights licence must be verified** | 2026-11-23 (doc-level; MUST VERIFY) | See JSON entry `whisper-weights`; do not bundle until verified | Audio local; no upload | User-supplied weights or another STT model | yes | X0.7; MPv5 §8 |
| Diarization models | Considered ("where licence allows") | **Many carry gated or non-commercial terms** | 2026-11-23 (doc-level; MUST VERIFY) | See JSON entry `diarization-models`; gate blocks bundling | Audio local; no upload | Drop diarization; keep plain local STT | yes | X0.7; base (M17 voice) |
| ffmpeg build flags (GPL vs LGPL) | Yes — **user-installed** ffmpeg | GPL builds are copyleft; prefer an LGPL build. Verify actual flags/build | 2026-11-23 (doc-level; MUST VERIFY) | See JSON entry `ffmpeg-build`; never bundle a GPL build | Local frame/audio extraction and subtitle generation; no upload | Require user-installed ffmpeg; feature degrades if absent | yes | X0.7; A3 (video tooling) |
| silero-vad (local voice activity detection) | Yes (voice pipeline) | Licence not pinned in metadata; verify | 2026-11-23 (doc-level; MUST VERIFY) | See JSON entry `silero-vad` | Audio local; no upload | Use a different VAD or skip VAD | yes | MPv5 §8 (free path defaults) |
| Work Sans / OFL fonts | Considered (a11y/dyslexia-friendly font option) | SIL OFL permits commercial use/redistribution with notices; font may not be sold alone; verify exact file/version | 2026-11-23 (doc-level; MUST VERIFY) | See JSON entry `work-sans-font`; retain OFL text and attribution | Bundled static asset only; no data flow | Use system fonts; drop bundled font | yes | X0.7; base (a11y font option) |
| ElevenLabs | **No — excluded** | Paid hosted service | 2026-11-23 (doc-level) | n/a | No user audio sent to any hosted TTS | Replaced by whisper.cpp + Piper/Kokoro | yes (not used) | X0.7; A4 §3; MPv5 §7.6 |
| OpenRouter / NVIDIA / Google Gemini / Anthropic / OpenAI / xAI-Grok (user-key adapters) | Optional adapters only | Each provider's own ToS/pricing; user's own account and key; never required or defaulted | 2026-11-23 (doc-level) | Provider API terms; no weights/code bundled | Prompts/data go to the third party only with the user's key + consent; redaction rules apply; no Keel-operated inference | Disable adapter; offline local model remains; four protocols (OpenAI Chat/Responses, Anthropic Messages, Gemini API) | yes | MPv5 §0.5, §7.6; A4 provider picker; A7 |
| pypdf (PDF text fallback) | Yes (bundled library) | Permissive OSS licence — verify exact version/licence at gate | 2026-11-23 (doc-level) | Retain licence notice in release notices/inventory | Local document parsing only; no upload | Replace with another local PDF library | no (bundled runtime library; not a service) | A4 Y1.4 (local PDF text fallback) |
| Pillow (image handling) | Yes (bundled library) | Permissive OSS licence — verify exact version/licence at gate | 2026-11-23 (doc-level) | Retain licence notice | Local image processing only | Replace with another local image library | no (bundled runtime library) | base (image/pipeline deps) |
| cryptography (AES-256-GCM at rest) | Yes (bundled library) | Permissive OSS licence (Apache-2.0/BSD-style) — verify exact version | 2026-11-23 (doc-level) | Retain licence + attribution notices | Local encryption of secrets with OS-keychain master key | Swap crypto backend; keep at-rest encryption | no (bundled runtime library) | base (secrets policy) |
| keyring (OS keychain master key) | Yes (bundled library) | Permissive OSS licence — verify exact version | 2026-11-23 (doc-level) | Retain licence notice | Master key stored in OS keychain; secrets never in repo; gitleaks per release | Use another OS-keystore backend | no (bundled runtime library) | MPv5 §8; base (secrets policy) |
| PyInstaller (Python packaging) | Yes (build tool) | Permissive OSS licence — verify exact version | 2026-11-23 (doc-level) | Retain licence notice in THIRD_PARTY_NOTICES | Build-time only; no runtime data flow | Use Nuitka or built-wheel packaging | no (build requirement, not a service) | MPv5 §8; A7 (built-wheel/PyInstaller smoke) |
| Nuitka (Python packaging/obfuscation) | Considered (alternative/obfuscation) | Apache-2.0-style licence (verify) | 2026-11-23 (doc-level) | Retain licence notice | Build-time only | Use PyInstaller instead | yes | MPv5 §8; base (Nuitka obfuscation) |
| electron-builder (desktop packaging) | Yes (build tool) | Permissive OSS licence — verify exact version | 2026-11-23 (doc-level) | Retain licence notice | Build-time only; produces NSIS/MSI, dmg, AppImage, deb, rpm | Swap packager; retain signed-artifact verification | no (build requirement, not a service) | MPv5 §8; A6 |
| Electron (desktop shell) | Yes (bundled runtime) | Permissive OSS licence — verify exact version | 2026-11-23 (doc-level) | Retain licence notice | Renderer/main process isolation; local loopback daemon with per-launch token | Web/PWA surface remains | no (bundled runtime) | MPv5 §8; A6 |
| gitleaks (secret scanning) | Yes (build/CI tool) | Permissive OSS licence — verify exact version | 2026-11-23 (doc-level) | Retain licence notice; reviewed `.gitleaksignore` with reason + expiry | Scans local repo/history; zero secrets in repo per release | Another secret scanner + local pre-push hooks | no (CI requirement, not a service) | X0.6; C11.1; base (gitleaks in CI) |
| pytest (test runner) | Yes (dev dependency) | Permissive OSS licence — verify exact version | 2026-11-23 (doc-level) | Retain licence notice | Local tests only | Another test runner | no (dev requirement, not a service) | X3/A3 adapters; A5 `pytest.ini`; A7 table-driven pytest |
| SpeechRecognition (Python STT library) | Considered | Permissive OSS licence — verify exact version | 2026-11-23 (doc-level) | Retain licence notice | Local audio handling; no upload | Prefer whisper.cpp; or substitute local STT | yes | base (voice pipeline) |
| Playwright + Chromium (E2E) | Yes (dev/CI dependency) | Permissive OSS licences — verify exact versions | 2026-11-23 (doc-level) | Retain licence notices | Local browser automation; consent for desktop control; no user data to third party | Use CDP/another browser engine (WebKit only for Keel web) | no (test requirement, not a service) | MPv5 §8; A4; A7 |
| Lighthouse (free audit) | Considered | Apache-2.0 per plan — **verify** | 2026-11-23 (doc-level; verify) | Retain Apache-2.0 notice | Local audit behind consent | Drop audit feature | yes | A4 |
| SQLite WAL + FTS5 + optional sqlite-vec | Yes (bundled database) | SQLite is permissive; sqlite-vec licence verify | 2026-11-23 (doc-level) | Retain licence notices | Local persistence/search; no data leaves the machine | Use plain SQLite; drop vec extension | no (bundled runtime library) | MPv5 §8 |
| OSV / pip-audit (dependency CVE scan) | Yes (optional offline OSV DB mirror) | Open databases/tools; verify terms | 2026-11-23 (doc-level) | Retain notices | Offline mirror optional; no source uploaded by default | Use another local scanner / SBOM-only | yes | base (supply chain; project security scans) |
| pyright / mypy / tsserver / gopls / rust-analyzer / tree-sitter (LSP/code intel) | Yes (dev tools) | Permissive OSS licences — verify each | 2026-11-23 (doc-level) | Retain licence notices | Local code intelligence; no code uploaded | Substitute per-language servers | no (dev requirements, not services) | MPv5 §8; base |
| OpenTelemetry (local spans) | Yes (local instrumentation) | Permissive OSS licence — verify | 2026-11-23 (doc-level) | Retain licence notice | Local spans only; no hosted telemetry backend | Disable telemetry | yes | MPv5 §8 |
| WASM / Pyodide sandbox (Code Mode) | Yes (sandbox runtime) | Permissive OSS licences — verify exact versions | 2026-11-23 (doc-level) | Retain licence notices | Generated code runs in a capability-limited sandbox; no filesystem/imports/timers | Fall back to direct tool listing (no Code Mode) | yes | A4 Y1.1; base B3.1 |
| MCP preset catalog (filesystem, git, fetch, SQLite, time, memory, Playwright, sequential-thinking, Linear free tier with user token) | Yes (user token for Linear) | Servers are free/self-hosted; Linear free tier with the user's own token; verify each server | 2026-11-23 (doc-level) | Per-server licences; retain notices | Presets are dormant until configured; tool calls gated by permissions; user token stays with user | Disable/remove presets | yes | A4 Y4.14; base (MCP presets) |
| LibreOffice (optional office preview/conversion) | Considered (native engine, WASM fallback) | Permissive OSS (MPL/LGPL-style) — verify | 2026-11-23 (doc-level; verify) | Retain licence notice | Local conversion; no cloud upload | Use WASM fallback or drop conversion | yes | A7 officeKit |

## Explicitly not taken (reference only)

From Master Plan §7.6 / Addendum 4 §3: Orgo cloud computers/credits, Composio, AgentMail,
AgentPhone, Linq, ElevenLabs, Latitude, 1Password, AgentCard, Honcho, Supabase, ngrok/cloudflared
accounts, hosted share/inference services, X API/vidiq/ideabrowser, and xAI/Grok/OpenAI/Anthropic
as required dependencies (optional user-key adapters only). Also excluded on purpose:
agent-controlled payments, unofficial WhatsApp libraries, and any feature sending user code to a
Keel-operated server.

## Re-verification checklist (per gate)

- [ ] Provider free-tier terms and commercial-use restrictions re-checked (X0.6).
- [ ] GitHub branch-protection / Actions-minute limits re-checked (the live 403 re-tested).
- [ ] Vercel Hobby non-commercial status → site migrated before charging anyone (D5).
- [ ] VirusTotal public API non-commercial status → adapter removed or confirmed optional.
- [ ] Docker Desktop licence posture → Podman/Docker Engine path confirmed.
- [ ] Every bundled model/voice/font/asset re-checked against `MODEL-AND-VOICE-LICENSES.json`
      and the CI gate (X0.7).
- [ ] Zero-network smoke still green with a local model (X0.8).
