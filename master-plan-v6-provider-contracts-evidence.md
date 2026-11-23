# Master Plan v6 — Provider Contracts Evidence (Addenda A5)

- **Branch:** `agent/a5-providers`
- **Baseline:** `9201f2a` (Mark W3/D2/Y1 batch — 44 P0 features verified)
- **Worktree:** `C:\Users\Admin\.local\share\opencode\worktree\addenda\a5-providers`
- **Feature IDs:** E6.1, E6.5, E6.8, E6.10 (P0, `not_started` in the 865-row registry)
- **Scope:** additive, stdlib-only configuration contracts for third-party model
  providers. No network, no credentials, no bundled/paid provider, no edits to
  any existing source or test file.

> Constraint honored: only the three files I own were added —
> `keel/src/keel/provider_contracts.py`,
> `keel/tests/test_provider_contracts.py`, and this evidence file. Existing
> modules were read only. Every place that must adopt the contract is specified
> exactly in §5 for the lead.

Commit SHA is reported in the agent's final message (no push performed).

---

## 1. Registry rows implemented (full text from `PLAN-INDEX.json`)

E6.9 is the only other E6.x row and was already `verified`; E6.2/3/4/6/7/11/12/14
are P1/P2 and out of scope. The four rows below are therefore the complete set
of `not_started` P0 E6.x features.

| ID | Registry requirement | Where satisfied |
|---|---|---|
| **E6.1** | Keys are write-only: UI receives a redacted descriptor, never the secret; settings store only a credential reference; masked preview = identifier prefix, 5 leading + 4 trailing only when ≥8 middle code points stay hidden, else all dots (Unicode code points). | `mask_secret`, `SecretDescriptor`, `describe_secret`, `redact_descriptor`, `credential_audit_record` |
| **E6.5** | Third-party picker from installed catalog vs Custom form: permanent lowercase provider ID, base URL, protocol, credential, models; four protocols; one protocol per provider; renaming = add new + delete old; no bundled/paid provider; explicit approval. | `ProviderDescriptor`, `provider_from_dict`, `search_catalog`, `ProviderRegistry`, `PROTOCOLS` |
| **E6.8** | Per-model input types (text/image), context window, max output, tool-call dialect hint, reasoning support; route-level defaultInput fallback that never removes images the catalog knows; per-model override; "claims … not verified" warning; image limits cleared when image removed. | `ModelCapabilities`, `merge_input_types`, `effective_input_types`, `without_image`, `capability_warning`, `capability_report` |
| **E6.10** | Request-compatibility switches (`supports_developer_role`, `max_tokens_field`, `thinking_format`, …) at route level with per-model field-by-field override; empty value refused, unknown name refused with list of valid names; each switch valid only for protocols that declare it; compat profile object + validation messages. | `CompatSwitches`, `CompatProfile`, `validate_switch`, `resolve_switches`, `adapt_request` |

E6.8's "image-refusal-before-send with clear message" is satisfied by
`image_preflight_message`; E6.10's "unsupported feature degrades honestly (no
silent drop)" is satisfied by `AdaptedRequest.adjustments`.

---

## 2. Design decisions

### 2.1 E6.1 — one-way secret flow

`describe_secret(name, secret, …)` is the **only** function that accepts a raw
value. It computes the masked hint and returns a frozen `SecretDescriptor`;
the value exists only in a local parameter and is never assigned to a field,
mapping, log line or exception message. `redact_descriptor()` returns exactly
`{name, source, masked_hint, reference}` — no `secret`/`value`/`api_key` key —
and `credential_audit_record()` returns exactly
`{"event": "credential.write", "name": ...}`.

Masking counts Unicode **code points** (`list(str)`), not UTF-8 bytes. With
`n >= 17` the hint is `identifier: <5 leading><n-9 dots><4 trailing>`; for
shorter values it is `identifier: <n dots>`. The `identifier: ` prefix is also
validated on manually constructed descriptors, so a raw key cannot be smuggled
in through `masked_hint`.

### 2.2 E6.5 — installed third-party catalog only

Canonical protocol IDs: `openai-chat-completions`, `openai-responses`,
`anthropic-messages`, `gemini-api`. `protocol` is a single string, so a gateway
serving two protocols must be registered twice (two ids). The id is a frozen,
lowercase slug; there is deliberately **no** `rename()` — the registry exposes
`add()`/`remove()` only. `bundled=True` and `paid=True` are rejected at
construction, and `search_catalog()` also filters such entries defensively.
`ProviderRegistry.add()` refuses a descriptor without `user_approved=True`.
Catalog search filters by capability and/or protocol and reports all valid
capability names for an unknown value.

### 2.3 E6.8 — typed claims with honest fallback

All capability fields are validated: positive integer `context_window` and
`max_output` (`max_output <= context_window`), non-empty input types restricted
to `text`/`image`, tool-call dialect from the known `model_dialects` vocabulary
plus `provider-native`/`none`, and boolean reasoning support. Image limits
(`max_images`, `image_max_bytes`) are legal only for image-capable models;
`without_image()` removes image input **and** clears those limits.
`effective_input_types()` unions route default + catalog knowledge + per-model
claim, so a text-only model override can never remove an image capability the
route or catalog knows. `capability_report()` always carries the exact warning
"…claims about your endpoint; they are not verified by Keel."

### 2.4 E6.10 — switches, overrides and honest degradation

Switch names: `supports_developer_role`, `max_tokens_field`, `thinking_field`,
`streaming_format` (`thinking_format` accepted as an alias). `PROTOCOL_SWITCHES`
declares which protocol supports which switch: developer role is OpenAI-only,
thinking is not declared by Gemini, all four declare max-token + streaming.
`validate_switch()` refuses empty values, unknown names (reporting every valid
name), and switches not declared by the given protocol (reporting that
protocol's valid switches).

A `CompatProfile` holds route defaults plus per-model `CompatSwitches`;
`resolve_switches()` merges field by field (only non-`None` override fields
win). `adapt_request()` deep-copies the request, renames known max-token and
thinking fields, clamps to `max_output`, maps unsupported developer roles to
`system`, can disable streaming, and **never** drops image content. Every one
of those changes is recorded in `AdaptedRequest.adjustments`; a removed
thinking parameter or disabled stream always produces a note.

---

## 3. Public API surface added

| Symbol | Kind | Feature |
|---|---|---|
| `SCHEMA_VERSION`, `MASK_CHAR`, `PROTOCOLS`, `CATALOG_CAPABILITIES`, `SWITCH_NAMES`, `PROTOCOL_SWITCHES`, `STREAMING_FORMATS`, `TOOL_DIALECT_HINTS`, `MAX_TOKEN_KEYS`, `THINKING_KEYS`, `UNVERIFIED_CLAIMS_WARNING` | constants | all |
| `ProviderContractError` | `ValueError` subclass | all |
| `mask_secret`, `describe_secret`, `redact_descriptor`, `credential_audit_record`, `secret_appears_in` | functions | E6.1 |
| `SecretDescriptor` | frozen dataclass | E6.1 |
| `ProviderDescriptor`, `provider_from_dict`, `search_catalog`, `validate_provider_descriptor`, `ProviderRegistry` | dataclass / functions / class | E6.5 |
| `ModelCapabilities`, `merge_input_types`, `effective_input_types`, `without_image`, `capability_warning`, `capability_report` | dataclass / functions | E6.8 |
| `CompatSwitches`, `CompatProfile`, `validate_switch`, `resolve_switches`, `AdaptedRequest`, `adapt_request`, `image_preflight_message` | dataclasses / functions | E6.10 |

Only stdlib imports: `copy`, `dataclasses`, `re`, `types`, `typing`,
`urllib.parse`. No import of `keel.providers`, `keel.webapp` or any credential
store — so the module cannot create a circular import or read a secret.

---

## 4. Tests and results

`keel/tests/test_provider_contracts.py` — 85 tests, all passing in 0.99s:

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_provider_contracts.py']))"
........................................................................ [ 84%]
.............                                                            [100%]
85 passed in 0.99s
```

Coverage by requirement (tests-first: the whole file was written before the
implementation module):

| Requirement | Representative tests |
|---|---|
| secret never appears in returned structure/log | `test_secret_never_appears_in_descriptors_or_redactions`, `test_redact_descriptor_exposes_only_public_fields`, `test_audit_record_records_name_only`, `test_secret_appears_in_walks_nested_structures` |
| masking rule / Unicode | `test_mask_secret_long_reveals_only_edges`, `test_mask_secret_boundary_at_seventeen_code_points`, `test_mask_secret_counts_unicode_code_points_not_bytes`, `test_mask_secret_short_is_all_dots` |
| invalid endpoints / protocols | `test_endpoint_must_be_https_without_credentials` (6 cases), `test_unknown_protocol_rejected_with_valid_list`, `test_one_protocol_per_provider_and_gateway_needs_two_ids` |
| provider id / approval / catalog | `test_provider_id_is_permanent_lowercase_slug` (5 cases), `test_explicit_user_approval_is_required_to_register`, `test_catalog_search_by_capability_filters_unapproved_kinds`, `test_registry_duplicate_remove_and_no_rename` |
| capability validation | `test_capabilities_reject_invalid_numeric_fields` (6 cases), `test_capabilities_reject_unknown_input_type_or_dialect` (4 cases), `test_image_limits_require_image_input`, `test_effective_input_types_uses_route_default_and_catalog_union`, `test_without_image_clears_image_limits` |
| switch edge cases | `test_empty_switch_value_refused` (3 cases), `test_unknown_switch_name_refused_with_valid_list`, `test_switch_valid_only_for_declaring_protocols`, `test_switch_value_types_and_allowlists` (5 cases), `test_compat_profile_field_by_field_override` |
| four provider styles | `test_adapt_request_openai_chat_completions_style`, `test_adapt_request_openai_responses_style`, `test_adapt_request_anthropic_messages_style`, `test_adapt_request_gemini_api_style_removes_thinking_with_note` |
| no silent drop / purity | `test_unsupported_feature_degrades_honestly_without_silent_drop`, `test_adapt_request_is_pure_and_does_not_mutate_input`, `test_image_preflight_refuses_before_send_and_never_drops_images` |

Regression smoke test (existing modules, read-only):

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q',
  'keel/tests/test_m2_provider_config.py','keel/tests/test_provider_sources.py',
  'keel/tests/test_providers.py','keel/tests/test_redaction.py',
  'keel/tests/test_secret_storage.py','keel/tests/test_provider_validation.py']))"
44 passed in 1.94s
```

No test was skipped or xfailed; no tool failed.

---

## 5. Integration seams for the lead (no edits made in this batch)

1. **E6.1 — `keel/src/keel/settings_store.py` / `keel/src/keel/webapp.py`.**
   `get_provider_config()` (settings_store.py:115) and the provider config write
   path (webapp.py:719-728) currently merge raw config objects. Store only
   `SecretDescriptor.reference` (e.g. `env:KEEL_ACME_KEY` or
   `settings://credentials/acme`) in `providerKeys`; never persist the value.
   Any provider-form response must call `redact_descriptor()`, and any write
   must append `credential_audit_record()` — both return only safe fields.
   `keel/src/keel/secret_store.py` remains the place that encrypts at rest; this
   module deliberately does not import it.

2. **E6.5 — `keel/src/keel/provider_catalog.py` / `keel/src/keel/webapp.py`.**
   `load_catalog()`/`provider_ids()` already expose an installed catalog; feed
   each record through `provider_from_dict()` and expose `search_catalog()` as
   the picker's search endpoint. The existing `/api/providers` route
   (webapp.py:384-388) can be extended to return `ProviderDescriptor.to_dict()`
   entries. The Custom Model API form should build the same descriptor with
   `user_approved=True` after the user confirms.

3. **E6.8 — `keel/src/keel/webapp.py` / `keel/src/keel/providers/model_client.py`.**
   Render `ModelCapabilities.to_dict()` in the model editor together with
   `capability_warning()`. Before streaming a turn, call
   `image_preflight_message(capabilities, request)` and show its message instead
   of sending an image to a text-only model. Resolve per-model input types with
   `effective_input_types(..., route_default=..., catalog_types=...)`.

4. **E6.10 — `keel/src/keel/config_schema.py` / provider config.**
   Add a `compatProfile` object built from `CompatProfile.to_dict()`; validate
   on every settings write with `validate_switch(name, value, protocol=...)`.
   In `keel/src/keel/providers/model_client.py::_complete_inner` (model_client.py:62),
   call `adapt_request(capabilities, request_dict, profile=...)` and surface the
   returned `adjustments` to the user (e.g. in the turn's diagnostic channel).
   `ModelCapabilities.tool_call_dialect` intentionally uses the same dialect
   names as `keel/src/keel/model_dialects.py::DIALECTS`, plus
   `provider-native`/`none`, so no translation table is needed at that seam.

---

## 6. Honest limitations

- Configuration contracts only: no provider is contacted and no key is read,
  decrypted or verified. The "not verified" warning is mandatory for a reason.
- `ProviderRegistry` is in-memory; persistence and UI approval flow belong to
  the lead's config work (§5). `ProviderDescriptor` is frozen so id immutability
  is structural, but a persistent store must also forbid id edits.
- `adapt_request()` handles the four documented switch families; it is not a
  full wire-format encoder for the four protocols. Unknown request keys are
  passed through unchanged and are not translated.
- These four registry rows are implemented and locally verified, but their
  status in `PLAN-INDEX.json` and the derived artifacts is still `not_started`
  by design — this agent does not own those generated files.
