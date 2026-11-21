# Patch policy

Third-party dependencies are used as published whenever possible. This folder
is reserved for **local patches only** and must stay empty unless a patch is
justified and recorded here.

A patch is acceptable only when:

1. the upstream behaviour is a blocker for a Keel requirement;
2. the library licence permits modification and redistribution;
3. the fix is minimal, reviewed, and covered by a test;
4. an issue or upstream PR reference is recorded beside the patch file;
5. the patch is re-checked on every dependency upgrade and removed when upstream
   ships the fix.

Patches must never:

- add telemetry, hosted infrastructure or credential collection;
- weaken Keel's permission, approval or safety model;
- introduce a paid or account-gated service.

Apply patches through the project's build tooling, never by editing installed
site-packages in place. Record the exact version range each patch targets in
the patch file header.
