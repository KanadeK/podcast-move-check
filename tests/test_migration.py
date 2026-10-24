from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

from podcast_move_check.core import InputError, Limits, compare_feeds, parse_feed, read_feed


def item(
    guid="episode-1",
    url="https://old.example.invalid/1.mp3",
    *,
    season="1",
    number="1",
    kind="full",
    date="Thu, 04 Jan 2024 12:00:00 GMT",
    permalink="false",
    title="Synthetic episode",
):
    fields = [f"<title>{escape(title)}</title>"]
    if guid is not None:
        fields.append(f"<guid isPermaLink={quoteattr(permalink)}>{escape(guid)}</guid>")
    if url is not None:
        fields.append(f'<enclosure url={quoteattr(url)} length="1234" type="audio/mpeg"/>')
    for name, value in (("season", season), ("episode", number), ("episodeType", kind)):
        if value is not None:
            fields.append(f"<itunes:{name}>{escape(value)}</itunes:{name}>")
    if date is not None:
        fields.append(f"<pubDate>{escape(date)}</pubDate>")
    return "<item>" + "".join(fields) + "</item>"


def rss(*items, show_guid="show-1"):
    marker = f"<podcast:guid>{escape(show_guid)}</podcast:guid>" if show_guid is not None else ""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" '
        'xmlns:podcast="https://podcastindex.org/namespace/1.0">'
        "<channel><title>Original synthetic show</title><link>https://example.invalid/</link>"
        "<description>Original fixtures; no real listener data.</description>"
        + marker
        + "".join(items)
        + "</channel></rss>"
    ).encode("utf-8")


def check(old, new, **kwargs):
    return compare_feeds(parse_feed(old), parse_feed(new), **kwargs)


def codes(report):
    return {row["code"] for row in report["findings"]}


class ContinuityTests(unittest.TestCase):
    def test_host_move_preserves_identity(self):
        result = check(rss(item()), rss(item(url="https://new.example.invalid/1.mp3")))
        self.assertTrue(result["passed"])
        self.assertEqual(result["preserved_identities"], 1)
        self.assertIn("enclosure_changed", codes(result))
        self.assertEqual(result["matches"][0]["basis"], "guid")

    def test_reorder_is_not_a_loss(self):
        one, two = item(), item("episode-2", "https://old.example.invalid/2.mp3", number="2")
        result = check(rss(one, two), rss(two, one))
        self.assertTrue(result["passed"])
        self.assertEqual(
            [(m["old_item"], m["new_item"]) for m in result["matches"]], [(1, 2), (2, 1)]
        )

    def test_changed_guid_with_exact_enclosure_evidence(self):
        result = check(rss(item()), rss(item("changed-guid")))
        self.assertFalse(result["passed"])
        self.assertIn("guid_changed", codes(result))
        self.assertEqual(result["matches"][0]["basis"], "enclosure_evidence")
        self.assertEqual(result["preserved_identities"], 0)

    def test_changed_guid_and_url_do_not_match_by_title(self):
        result = check(rss(item()), rss(item("changed", "https://new.example.invalid/1.mp3")))
        self.assertFalse(result["passed"])
        self.assertEqual(result["matched_items"], 0)
        self.assertEqual(codes(result), {"unmatched_old_item", "unmatched_target_item"})

    def test_missing_episode_fails_new_episode_is_advisory(self):
        one, two = item(), item("episode-2", "https://old.example.invalid/2.mp3", number="2")
        self.assertFalse(check(rss(one, two), rss(one))["passed"])
        extra = check(rss(one), rss(one, two))
        self.assertTrue(extra["passed"])
        self.assertEqual(extra["unmatched_target_items"], 1)

    def test_duplicate_guid_never_chooses_arbitrary_target(self):
        duplicate = item("episode-1", "https://old.example.invalid/2.mp3")
        for old, new in (
            (rss(item(), duplicate), rss(item())),
            (rss(item()), rss(item(), duplicate)),
        ):
            with self.subTest(old=old):
                result = check(old, new)
                self.assertFalse(result["passed"])
                self.assertIn("duplicate_guid", codes(result))
                self.assertEqual(result["matched_items"], 0)

    def test_duplicate_enclosure_is_not_guid_change_evidence(self):
        result = check(rss(item("a"), item("b")), rss(item("c"), item("d")))
        self.assertFalse(result["passed"])
        self.assertEqual(result["matched_items"], 0)
        self.assertNotIn("guid_changed", codes(result))

    def test_no_guid_requires_explicit_legacy_mode(self):
        old = rss(item(None))
        self.assertFalse(check(old, old)["passed"])
        accepted = check(old, old, allow_enclosure_identity=True)
        self.assertTrue(accepted["passed"])
        self.assertEqual(accepted["matches"][0]["basis"], "enclosure_identity")
        self.assertGreater(accepted["counts"]["warning"], 0)
        self.assertFalse(check(old, old, allow_enclosure_identity=True, strict=True)["passed"])

    def test_legacy_url_move_cannot_be_proven(self):
        result = check(
            rss(item(None)),
            rss(item(None, "https://new.example.invalid/a.mp3")),
            allow_enclosure_identity=True,
        )
        self.assertFalse(result["passed"])
        self.assertEqual(result["preserved_identities"], 0)

    def test_added_or_removed_guid_is_identity_source_change(self):
        for old, new in ((item(None), item()), (item(), item(None))):
            result = check(rss(old), rss(new), allow_enclosure_identity=True)
            self.assertFalse(result["passed"])
            self.assertIn("identity_source_changed", codes(result))

    def test_numbering_and_type_must_survive(self):
        for field, value, code in (
            ("season", None, "season_changed"),
            ("number", "2", "episode_number_changed"),
            ("kind", "bonus", "episode_type_changed"),
        ):
            result = check(rss(item()), rss(item(**{field: value})))
            self.assertFalse(result["passed"])
            self.assertIn(code, codes(result))

    def test_numeric_equivalents_and_default_full_type(self):
        result = check(rss(item(season="01", number="001")), rss(item(kind=None)))
        self.assertTrue(result["passed"])
        self.assertEqual(result["counts"]["warning"], 0)

    def test_show_guid_removal_or_change_fails(self):
        for guid in (None, "different-show"):
            result = check(rss(item()), rss(item(), show_guid=guid))
            self.assertFalse(result["passed"])
            self.assertIn("show_guid_changed", codes(result))

    def test_permalink_change_warning_and_strict(self):
        old, new = rss(item()), rss(item(permalink="true"))
        self.assertTrue(check(old, new)["passed"])
        self.assertIn("guid_permalink_changed", codes(check(old, new)))
        self.assertFalse(check(old, new, strict=True)["passed"])

    def test_same_pubdate_in_different_timezone(self):
        result = check(rss(item()), rss(item(date="Thu, 04 Jan 2024 07:00:00 -0500")))
        self.assertNotIn("pubdate_changed", codes(result))

    def test_invalid_pubdate_numbering_and_type_warn(self):
        data = rss(item(date="not-a-date", number="one", kind="unknown"))
        result = check(data, data)
        self.assertTrue(result["passed"])
        self.assertTrue(
            {"invalid_pubdate", "invalid_episode_numbering", "invalid_episode_type"}
            <= codes(result)
        )
        self.assertFalse(check(data, data, strict=True)["passed"])

    def test_guid_case_and_unicode_are_opaque(self):
        for before, after in (("episode-a", "EPISODE-A"), ("caf\u00e9", "cafe\u0301")):
            result = check(rss(item(before)), rss(item(after)))
            self.assertIn("guid_changed", codes(result))

    def test_guid_whitespace_is_not_silently_normalized(self):
        result = check(rss(item(" episode-1 ")), rss(item()))
        self.assertFalse(result["passed"])
        self.assertIn("guid_surrounding_whitespace", codes(result))
        self.assertIn("guid_changed", codes(result))

    def test_report_does_not_disclose_identifiers_urls_or_titles(self):
        raw_guid, raw_url = (
            "private-id-synthetic",
            "https://example.invalid/audio?synthetic-token=x",
        )
        result = check(
            rss(item(raw_guid, raw_url, title="private title synthetic")),
            rss(item("new-id", raw_url)),
        )
        serialized = json.dumps(result)
        for value in (raw_guid, raw_url, "private title synthetic", "new-id"):
            self.assertNotIn(value, serialized)

    def test_missing_and_non_http_enclosures_fail(self):
        for url in (
            None,
            "file:///unread",
            "javascript:unexecuted",
            "https://bad.example/a b",
            "https://[",
        ):
            result = check(rss(item()), rss(item(url=url)))
            self.assertFalse(result["passed"])
            self.assertIn("missing_or_invalid_enclosure", codes(result))

    def test_enclosure_swapped_between_guid_preserved_episodes(self):
        old = rss(
            item("a", "https://old.example.invalid/a.mp3"),
            item("b", "https://old.example.invalid/b.mp3"),
        )
        new = rss(
            item("a", "https://old.example.invalid/b.mp3"),
            item("b", "https://old.example.invalid/a.mp3"),
        )
        result = check(old, new)
        self.assertFalse(result["passed"])
        self.assertIn("enclosure_reassigned", codes(result))

    def test_empty_old_rejected_empty_target_fails(self):
        with self.assertRaises(InputError):
            check(rss(), rss())
        self.assertFalse(check(rss(item()), rss())["passed"])

    def test_findings_and_matches_truncate_without_hiding_totals(self):
        old = rss(
            item("a", "https://old.example.invalid/a"), item("b", "https://old.example.invalid/b")
        )
        failed = check(old, rss(), limits=Limits(max_findings=1))
        self.assertFalse(failed["passed"])
        self.assertEqual(failed["counts"]["error"], 2)
        self.assertTrue(failed["findings_truncated"])
        passed = check(old, old, limits=Limits(max_matches=1))
        self.assertTrue(passed["passed"])
        self.assertEqual(passed["preserved_identities"], 2)
        self.assertTrue(passed["matches_truncated"])

    def test_reports_are_deterministic(self):
        old, new = rss(item()), rss(item("changed"))
        self.assertEqual(check(old, new), check(old, new))


class ParserAndCLITests(unittest.TestCase):
    def test_dtd_entity_and_external_entity_rejected(self):
        for declaration in (
            '<!DOCTYPE rss [<!ENTITY x "expanded">]>',
            '<!DOCTYPE rss SYSTEM "file:///unread">',
            '<!ENTITY x SYSTEM "https://example.invalid/unfetched">',
        ):
            data = rss(item()).replace(b"<rss ", declaration.encode() + b"<rss ", 1)
            with self.subTest(declaration=declaration), self.assertRaises(InputError):
                parse_feed(data)

    def test_utf8_bom_supported_utf16_and_other_decl_rejected(self):
        self.assertEqual(len(parse_feed(b"\xef\xbb\xbf" + rss(item())).episodes), 1)
        for data in (
            rss(item()).decode().encode("utf-16"),
            rss(item()).replace(b"UTF-8", b"ISO-8859-1"),
            b"\xff",
        ):
            with self.subTest(data=data[:20]), self.assertRaises(InputError):
                parse_feed(data)

    def test_malformed_or_wrong_format_xml_rejected(self):
        cases = [
            b"",
            b"<rss",
            b'<feed xmlns="http://www.w3.org/2005/Atom"/>',
            b'<rss version="1.0"><channel/></rss>',
            b'<rss version="2.0"><channel/><channel/></rss>',
        ]
        for data in cases:
            with self.subTest(data=data), self.assertRaises(InputError):
                parse_feed(data)

    def test_repeated_guid_enclosure_and_nested_identity_rejected(self):
        base = item()
        for extra in ("<guid>another</guid>", '<enclosure url="https://example.invalid/x"/>'):
            with self.subTest(extra=extra), self.assertRaises(InputError):
                parse_feed(rss(base.replace("</item>", extra + "</item>")))
        with self.assertRaises(InputError):
            parse_feed(rss(base.replace("episode-1", "<b>nested</b>")))

    def test_bytes_nodes_depth_and_item_limits(self):
        for limits in (
            Limits(max_bytes=1),
            Limits(max_nodes=2),
            Limits(max_depth=2),
            Limits(max_items=1),
        ):
            with self.subTest(limits=limits), self.assertRaises(InputError):
                parse_feed(rss(item(), item("two")), limits=limits)

    def test_invalid_permalink_is_error(self):
        data = rss(item(permalink="maybe"))
        self.assertFalse(check(data, data)["passed"])

    def test_file_input_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "snapshot.xml"
            original = rss(item())
            path.write_bytes(original)
            self.assertEqual(len(read_feed(path).episodes), 1)
            self.assertEqual(path.read_bytes(), original)

    def test_cli_process_exit_codes_and_privacy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old, new = root / "old.xml", root / "new.xml"
            old.write_bytes(rss(item()))
            for data, expected in ((rss(item()), 0), (rss(item("changed")), 1), (b"corrupt", 2)):
                new.write_bytes(data)
                result = subprocess.run(
                    [sys.executable, "-m", "podcast_move_check", str(old), str(new), "--json"],
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(result.returncode, expected, result.stderr)
                report = json.loads(result.stdout)
                self.assertEqual(report["passed"], expected == 0)
                self.assertNotIn(b"episode-1", result.stdout)


if __name__ == "__main__":
    unittest.main()
