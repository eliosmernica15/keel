# Agent Notes (ADR-like) — D6.17

Owner: Agent H. Audited 2026-11-24.

## Rule

Write an Agent Note only for a **durable decision rationale** that a future
builder would otherwise re-litigate: the options considered, the chosen option,
who approved it, and what evidence or constraint drove it. Do not use notes for
progress updates, task status, meeting summaries or anything that changes from
day to day.

- Active notes are living files, but only the rationale may be amended, with
  the date and reason recorded in the same entry. Never rewrite history to make
  a past decision look current.
- An archived note is frozen. It is evidence of what was decided then, **not**
  current authority. If the decision changes, add a new note that supersedes it
  with a dated link; do not edit the archive.
- Owner-level decisions stay in `DECISIONS.md`; Agent Notes describe builder
  rationale and point to the owner record when one exists.

## What exists in this tree today

| Note | Status | Why it qualifies |
|---|---|---|
| `DECISIONS.md` D-036 (Y6.4 public repo) | active owner decision, dated | Two alternatives, private-source owner gate G1, explicit "do not implement" resolution and approval requirement. |
| `DECISIONS.md` D-037 (W1.18 MIT license) | active owner decision, dated | Conflicting plan rows, two alternatives, legal implication for Keel code, owner gate G7. |
| `keel/docs/plan-sources/*.md` (8 source documents) | frozen archive | Preserved verbatim as source material; they are *not* current requirements. Conflicts are resolved in `DECISIONS.md` and `Keel_Master_Plan_v6.md`, never by editing these files. |
| `keel/docs/proprietary/*.draft.md` | drafts, not authority | Marked DRAFT / not published; must not be quoted as an approved license or notice. |

## Entry format (for new notes)

```
## <short decision title> — YYYY-MM-DD
- Question: <what had to be decided>
- Options: <a>; <b> (<c> …)
- Decision: <chosen option>
- Rationale / evidence: <files, commands or owner gate that drove it>
- Owner / approver: <owner gate or role; "builder" if no owner gate>
- Supersedes / superseded by: <note id or "none">
- Status: active | archived (frozen)
```

## Evidence boundary

This round added the convention and a place to record it. No existing owner
decision was edited, and no archived source document was touched. The
documentation/governance reconciliation in
`keel/docs/MASTER-PLAN-INVENTORY.md` records which decisions remain owner-gated.
