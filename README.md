# podcast-move-check

Check episode identity and continuity **before moving a podcast between hosts**.
Compare two local RSS 2.0 snapshots offline, using a hardened XML parser.

[中文说明](README.zh-CN.md) · [Security](SECURITY.md) · [Contributing](CONTRIBUTING.md)

A feed may remain valid XML while a migration changes episode GUIDs, drops old
episodes or swaps enclosure assignments. Those changes are easy to miss in a large
XML diff. This tool makes preservation of the supplied old snapshot an explicit gate.
It reports item positions, without copying episode IDs, titles or media URLs into logs.

## Install

Python 3.11+ is required. Installation adds the small `defusedxml==0.7.1` dependency;
operation is offline. No hosting account, API key, audio download or server is needed.

```sh
git clone https://github.com/KanadeK/podcast-move-check.git
cd podcast-move-check
python -m venv .venv
# Linux/macOS:
. .venv/bin/activate
# Windows PowerShell instead:
# .\.venv\Scripts\Activate.ps1
python -m pip install .
podcast-move-check --version
```

You can also run `.venv/bin/python -m podcast_move_check` or
`.\.venv\Scripts\python.exe -m podcast_move_check` without activation. GitHub Releases
include wheels that install with `python -m pip install path/to/downloaded.whl`.
This is not a claim that a PyPI package has been published.

## Compare the actual migration snapshots

Save your old feed **before** changing hosts. Save the proposed new feed separately,
using your provider's export or your normal download tool. This CLI only reads files:

```sh
podcast-move-check old.xml proposed.xml
podcast-move-check old.xml proposed.xml --json
podcast-move-check old.xml proposed.xml --strict
```

Item numbers are 1-based positions in each snapshot, so reordering does not itself
fail. A passing check establishes the documented contract for these two files only.
It cannot know about episodes already absent from the old snapshot. Compare complete
exports where your migration is intended to retain the complete archive.

### What is blocking

- Missing or duplicate episode GUIDs, invalid/missing HTTP(S) enclosures and invalid
  `isPermaLink` values.
- An old episode with no unique matching GUID or exact enclosure evidence.
- A changed GUID when a unique, unchanged enclosure identifies the corresponding item.
- Adding/removing the GUID identity source, or reassigning another old episode's
  unique enclosure URL to a different preserved GUID.
- Loss/change of old iTunes season/episode numbering or episode type; a changed/removed
  existing Podcasting 2.0 show GUID.

GUIDs are opaque and compared exactly, including case, Unicode and surrounding
whitespace. Numbering is compared numerically when it contains up to 12 decimal digits;
missing episode type means `full`. A changed enclosure URL for a preserved GUID is
informational: normal host migration changes media addresses.

### What is advisory

Media type/length, publication instant and `isPermaLink` changes; invalid dates,
numbering or type; repeated enclosure URLs; and GUID whitespace generate warnings.
Additional unmatched target items are informational. `--strict` also fails on warnings.
Publication times are compared in UTC when both can be parsed with explicit timezones.

If both GUID and URL change, this tool reports an unmatched old and target item. It
does not guess a pairing from title or episode position. Exact enclosure evidence
indicates a migration identity risk; it is not proof of byte-identical audio.

Legacy feeds without GUIDs fail by default. An explicit opt-in can accept identities
based on unique, exact enclosure URLs in **both** snapshots:

```sh
podcast-move-check old.xml proposed.xml --allow-enclosure-identity
```

Missing GUIDs remain warnings, and adding/removing a GUID still fails. This mode does
not establish Apple Podcasts compliance or justify moving a GUID-less feed's URLs.

## Runnable example

After installation, from this repository:

```sh
python examples/demo.py .demo
```

The demo copies three original, synthetic feeds into a new directory. It invokes the
real CLI twice: a host change with stable GUID passes (exit `0`); a changed GUID with
the old enclosure retained fails (exit `1`). It verifies both return codes. No real
podcast feed or third-party episode content is bundled.

## Output contract

| Exit | Meaning |
|---|---|
| 0 | Supplied snapshots pass the selected continuity policy |
| 1 | Check completed and found blocking errors (or warnings with `--strict`) |
| 2 | Unreadable, unsupported, ambiguous or over-limit input; check incomplete |

JSON schema `podcast-move-check/v1` includes old/new counts, preserved identities,
matched/unmatched counts, severity totals, findings and match evidence. Findings use
stable `code`, `severity`, `old_item` and/or `new_item`. Matches identify `guid`,
`enclosure_evidence` or opted-in `enclosure_identity` as the basis.

Only the first 200 findings and first 200 match records are displayed. Totals cover
the complete check, and `findings_truncated` / `matches_truncated` make clipping
explicit. Hidden errors still fail. Reports contain item counts and positions but
omit raw IDs, URLs, dates, titles, description bodies and feed paths on successful
parsing. I/O errors can include the input filename. Keep even minimized reports local
when those counts are sensitive.

## Supported input and limits

Version 0.1.0 supports UTF-8 RSS 2.0, ordinary unnamespaced `item`/`guid`/`enclosure`,
the standard `http://www.itunes.com/dtds/podcast-1.0.dtd` namespace and
`https://podcastindex.org/namespace/1.0`. Atom, RSS 1.0, other encodings and repeated
identity/comparison elements are rejected. UTF-8 BOM is accepted.

Per snapshot limits: 16 MiB, 50,000 items, 200,000 elements, depth 64 and 8,192
characters per parsed text identity/comparison field. DTD/entity declaration markers
and NULs are rejected before XML parsing; this intentionally also rejects those literal
markers inside comments or CDATA. External entities and XInclude are never resolved.
Parsing also uses `defusedxml` with DTDs, entities and external references explicitly
forbidden. Input is held in memory; these limits are not a process-memory sandbox.

This is a migration contract check, not a complete RSS/platform validator. It does
not fetch feeds, test 301 redirects, compare audio bytes, prove hosting availability,
preserve analytics, verify ownership, change subscriptions or modify feeds.

## Tests, cleanup and references

Development checks are in [CONTRIBUTING.md](CONTRIBUTING.md). Tests cover reorder,
identity ambiguity, missing history, numeric markers, enclosure reassignment, XML
attacks, resource limits, minimized reporting and real CLI exit codes. CI runs Python
3.11 and 3.13 on Linux, macOS and Windows, with read-only repository permissions.

Uninstall with `python -m pip uninstall podcast-move-check`. Delete the dedicated
virtual environment and `.demo` if no longer needed. No cache, service, hooks,
credentials or global configuration are created. Your saved feeds remain your files.

[Apple's migration guide](https://podcasters.apple.com/support/3965-how-to-change-hosting-providers)
explains why stable episode identifiers matter. The [RSS specification](https://www.rssboard.org/rss-specification)
defines the input format. For feed generation and broad platform validation, consider
the more comprehensive [podcast-feed-maker](https://github.com/atelier-socle/podcast-feed-maker).
Our narrower gate emphasizes unambiguous identity evidence, preserved old history and
reports without feed identifiers. Code and synthetic fixtures are MIT-licensed;
[third-party provenance](THIRD_PARTY.md) is documented separately.
