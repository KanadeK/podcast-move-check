# Changelog

## 0.1.0 — 2026-10-24

- Check old episode continuity against a proposed RSS 2.0 migration snapshot.
- Separate stable GUIDs, exact enclosure evidence of GUID changes and unmatched history.
- Reject duplicate identities and enclosure reassignment; preserve show GUID and episode markers.
- Provide minimized deterministic reports, explicit legacy mode and stable CI exit codes.
- Parse XML with `defusedxml`, disabling DTDs, entities and external references with input limits.
- Include synthetic pass/fail demos, 32 tests and a read-only six-job CI matrix.

Initial scope is local UTF-8 RSS 2.0 snapshots. Live redirects, audio identity,
hosting behavior, complete platform validation, Atom and RSS 1.0 are not checked.
