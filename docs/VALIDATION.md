# Initial release validation

Local release checks on 2026-10-24 used Windows and CPython 3.13.16.

- All 32 unit/integration/CLI tests passed after installation into a new virtual environment.
- The runnable CLI demo verified both stable-identity success and changed-GUID failure.
- Ruff lint/security rules, formatting and byte compilation passed without disabling XML warnings.
- Source distribution and wheel built; a fresh installation from a local wheel directory
  succeeded with the network index disabled. Version and uninstall checks passed.
- The sole runtime dependency, `defusedxml==0.7.1`, was scanned with pip-audit; no known
  vulnerabilities were reported for that dependency at validation time. Its PSF license
  and upstream notice remain part of the separately installed dependency.
- A local snapshot of [The Changelog's public RSS](https://changelog.com/podcast/feed)
  contained 1,016 items. Comparing it with itself preserved all identities with zero
  errors/warnings. A synthetic alteration of one GUID, keeping enclosure evidence,
  was detected. The feed content is not redistributed in this repository or release.
- A separate original 5,000-episode synthetic snapshot preserved all identities and
  exercised bounded report truncation. This is a scale probe, not a general benchmark.

Review replaced the initial XML parser with an explicitly hardened parser, checked
opaque GUID handling and ambiguity, and added enclosure reassignment detection.
The report describes only supplied snapshots, not live migration success.

The repository's Actions page provides actual platform results. Local Windows checks
alone do not establish Linux or macOS behavior.
