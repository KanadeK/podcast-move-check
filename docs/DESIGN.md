# Contract and review boundaries

The target user is a podcaster reviewing a proposed hosting migration. Acceptance is
stable old identities and episode markers, with explicit failures for ambiguity and
missing old coverage. Additional target items are allowed. Inputs and policy are
read-only; a passing report never certifies live redirects or audio equivalence.

RSS input is decoded as UTF-8, then NUL/DTD/entity declarations are rejected before
the XML parser runs. Parsing uses `defusedxml` with all DTD/entity/external-reference
features explicitly forbidden. Element count/depth/item limits are checked during
parsing, with a file byte bound before parsing. Conservative marker rejection also
rejects literal DTD markers in CDATA/comments. No external entity or XInclude API is
called. Security review replaced the initial standard-library parsing call with the
mature hardened parser while retaining byte, depth and node bounds.

Identity joins prefer unique exact GUIDs. A unique exact enclosure can establish
evidence of a changed GUID, but title similarity is never treated as identity proof.
All instances of a duplicate GUID are excluded from automatic pairing. Legacy
enclosure-only matching requires explicit opt-in and still checks uniqueness.
Show GUID, season, episode and type continuity are checked separately.

Findings and matches retain only item positions, evidence type and static codes.
Counters are independent of display truncation. Reports are deterministic, with no
current-clock value, machine path, raw media URL, GUID, title or description body.

The implementation uses dictionaries/counters rather than pairwise item scans and
orders match output by the old item index. Bounded XML and emitted reports still
consume memory. Default scopes and deliberate omissions are in README.
