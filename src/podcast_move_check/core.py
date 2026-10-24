"""Strict, offline comparison of podcast identities in supplied RSS snapshots."""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from datetime import UTC
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlsplit

from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException

SCHEMA = "podcast-move-check/v1"
ITUNES = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"
PODCAST = "{https://podcastindex.org/namespace/1.0}"


class InputError(ValueError):
    """A snapshot cannot be safely or unambiguously interpreted."""


@dataclass(frozen=True)
class Limits:
    max_bytes: int = 16 * 1024 * 1024
    max_items: int = 50_000
    max_nodes: int = 200_000
    max_depth: int = 64
    max_findings: int = 200
    max_matches: int = 200

    def __post_init__(self) -> None:
        if any(type(v) is not int or v <= 0 for v in vars(self).values()):
            raise InputError("Limits must be positive integers")


@dataclass(frozen=True)
class Episode:
    index: int
    guid: str | None
    permalink: str
    enclosure: str | None
    media_type: str | None
    length: str | None
    season: str | None
    number: str | None
    kind: str
    published: str | None


@dataclass(frozen=True)
class Feed:
    episodes: tuple[Episode, ...]
    show_guid: str | None


def _one(parent: ET.Element, name: str) -> ET.Element | None:
    elements = parent.findall(name)
    if len(elements) > 1:
        raise InputError("Repeated identity or comparison field is ambiguous")
    return elements[0] if elements else None


def _text(parent: ET.Element, name: str, *, exact: bool = False) -> str | None:
    element = _one(parent, name)
    if element is None:
        return None
    if len(element):
        raise InputError("Identity/comparison fields must contain text, not child markup")
    text = element.text or ""
    if len(text) > 8192:
        raise InputError("Identity/comparison field exceeds 8192 characters")
    if not text.strip():
        return None
    return text if exact else text.strip()


def _number(value: str | None) -> str | None:
    # Season/episode numbers are numeric metadata, unlike opaque GUIDs.
    if value and re.fullmatch(r"[0-9]{1,12}", value):
        return str(int(value))
    return value


def parse_feed(data: bytes, *, limits: Limits | None = None) -> Feed:
    limits = limits or Limits()
    if len(data) > limits.max_bytes:
        raise InputError("RSS snapshot exceeds configured byte limit")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise InputError("Only UTF-8 RSS snapshots are supported") from exc
    if "\x00" in text or re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", text, re.I):
        raise InputError("NULs, DTDs and entity declarations are forbidden")
    declaration = re.match(r"\s*<\?xml\b([^?]*)\?>", text)
    if declaration:
        encoding = re.search(r"encoding\s*=\s*['\"]([^'\"]+)['\"]", declaration[1], re.I)
        if encoding and encoding[1].lower() not in ("utf-8", "utf8"):
            raise InputError("XML encoding declaration must be UTF-8")
    root = None
    nodes = depth = item_count = 0
    try:
        for event, element in SafeET.iterparse(
            io.StringIO(text),
            events=("start", "end"),
            forbid_dtd=True,
            forbid_entities=True,
            forbid_external=True,
        ):
            if event == "start":
                if root is None:
                    root = element
                nodes += 1
                depth += 1
                if element.tag == "item" and depth == 3:
                    item_count += 1
                if (
                    nodes > limits.max_nodes
                    or depth > limits.max_depth
                    or item_count > limits.max_items
                ):
                    raise InputError("RSS exceeds configured node, depth or episode limit")
            else:
                depth -= 1
    except ET.ParseError as exc:
        raise InputError(f"Malformed RSS XML at line/column {exc.position}") from exc
    except DefusedXmlException as exc:
        raise InputError("DTD, entity or external-reference XML is forbidden") from exc
    if root is None or root.tag != "rss" or root.get("version") != "2.0":
        raise InputError("Expected an RSS 2.0 document (Atom/RSS 1.0 are unsupported)")
    channels = root.findall("channel")
    if len(channels) != 1:
        raise InputError("RSS must have exactly one channel")
    channel = channels[0]
    episodes = []
    for index, item in enumerate(channel.findall("item"), 1):
        guid = _text(item, "guid", exact=True)
        guid_element = _one(item, "guid")
        enclosure = _one(item, "enclosure")
        published = _text(item, "pubDate")
        episodes.append(
            Episode(
                index=index,
                guid=guid,
                permalink=guid_element.get("isPermaLink", "true")
                if guid_element is not None
                else "true",
                enclosure=enclosure.get("url") if enclosure is not None else None,
                media_type=enclosure.get("type") if enclosure is not None else None,
                length=enclosure.get("length") if enclosure is not None else None,
                season=_number(_text(item, ITUNES + "season")),
                number=_number(_text(item, ITUNES + "episode")),
                kind=_text(item, ITUNES + "episodeType") or "full",
                published=published,
            )
        )
    return Feed(tuple(episodes), _text(channel, PODCAST + "guid", exact=True))


def read_feed(path: Path, *, limits: Limits | None = None) -> Feed:
    limits = limits or Limits()
    with path.open("rb") as stream:
        data = stream.read(limits.max_bytes + 1)
    return parse_feed(data, limits=limits)


def _date(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(UTC).isoformat()
    except (ValueError, TypeError, OverflowError):
        return None


def _http_url(value: str | None) -> bool:
    if not value or len(value) > 8192 or any(ord(c) <= 32 or ord(c) == 127 for c in value):
        return False
    try:
        parsed = urlsplit(value)
        return parsed.scheme.lower() in ("http", "https") and bool(parsed.hostname)
    except ValueError:
        return False


def compare_feeds(
    old: Feed,
    new: Feed,
    *,
    allow_enclosure_identity: bool = False,
    strict: bool = False,
    limits: Limits | None = None,
) -> dict:
    limits = limits or Limits()
    if not old.episodes:
        raise InputError("Old snapshot has no episodes; migration continuity cannot be established")
    findings = []
    counts: Counter = Counter()

    def finding(
        code: str, severity: str, old_item: int | None = None, new_item: int | None = None
    ) -> None:
        counts[severity] += 1
        if len(findings) < limits.max_findings:
            row = {"code": code, "severity": severity}
            if old_item is not None:
                row["old_item"] = old_item
            if new_item is not None:
                row["new_item"] = new_item
            findings.append(row)

    for side, feed in (("old", old), ("new", new)):
        guid_counts = Counter(e.guid for e in feed.episodes if e.guid is not None)
        url_counts = Counter(e.enclosure for e in feed.episodes if e.enclosure is not None)
        for item in feed.episodes:
            position = {side + "_item": item.index}
            if item.guid is None:
                finding(
                    "missing_guid", "warning" if allow_enclosure_identity else "error", **position
                )
            elif guid_counts[item.guid] > 1:
                finding("duplicate_guid", "error", **position)
            if item.guid and item.guid != item.guid.strip():
                finding("guid_surrounding_whitespace", "warning", **position)
            if item.permalink not in ("true", "false"):
                finding("invalid_guid_permalink", "error", **position)
            if not _http_url(item.enclosure):
                finding("missing_or_invalid_enclosure", "error", **position)
            elif url_counts[item.enclosure] > 1:
                finding("duplicate_enclosure", "warning", **position)
            if item.length is not None and not re.fullmatch(r"[0-9]{1,19}", item.length):
                finding("invalid_enclosure_length", "warning", **position)
            if item.published is not None and _date(item.published) is None:
                finding("invalid_pubdate", "warning", **position)
            if any(
                value is not None and not re.fullmatch(r"[0-9]{1,12}", value)
                for value in (item.season, item.number)
            ):
                finding("invalid_episode_numbering", "warning", **position)
            if item.kind not in ("full", "trailer", "bonus"):
                finding("invalid_episode_type", "warning", **position)
    if old.show_guid is not None and old.show_guid != new.show_guid:
        finding("show_guid_changed", "error")
    old_guids = Counter(e.guid for e in old.episodes if e.guid is not None)
    new_guids = Counter(e.guid for e in new.episodes if e.guid is not None)
    old_urls = Counter(e.enclosure for e in old.episodes if e.enclosure is not None)
    new_urls = Counter(e.enclosure for e in new.episodes if e.enclosure is not None)
    new_by_guid = {e.guid: e for e in new.episodes if e.guid is not None and new_guids[e.guid] == 1}
    new_by_url = {
        e.enclosure: e for e in new.episodes if e.enclosure and new_urls[e.enclosure] == 1
    }
    old_by_url = {
        e.enclosure: e for e in old.episodes if e.enclosure and old_urls[e.enclosure] == 1
    }
    pairs: list[tuple[Episode, Episode, str, bool]] = []
    used_old, used_new = set(), set()
    for item in old.episodes:
        if item.guid and old_guids[item.guid] == 1 and item.guid in new_by_guid:
            target = new_by_guid[item.guid]
            pairs.append((item, target, "guid", True))
            used_old.add(item.index)
            used_new.add(target.index)
    for item in old.episodes:
        if item.index in used_old or not item.enclosure or old_urls[item.enclosure] != 1:
            continue
        if item.guid and old_guids[item.guid] != 1:
            continue
        target = new_by_url.get(item.enclosure)
        if (
            target is None
            or target.index in used_new
            or (target.guid and new_guids[target.guid] != 1)
        ):
            continue
        if item.guid is None and target.guid is None:
            preserved = allow_enclosure_identity
            basis = "enclosure_identity"
        else:
            preserved = False
            basis = "enclosure_evidence"
            code = "guid_changed" if item.guid and target.guid else "identity_source_changed"
            finding(code, "error", item.index, target.index)
        pairs.append((item, target, basis, preserved))
        used_old.add(item.index)
        used_new.add(target.index)
    for item, target, _, _ in pairs:
        if item.enclosure != target.enclosure:
            finding("enclosure_changed", "info", item.index, target.index)
            previous_owner = old_by_url.get(target.enclosure)
            if previous_owner is not None and previous_owner.index != item.index:
                finding("enclosure_reassigned", "error", item.index, target.index)
        if item.media_type != target.media_type:
            finding("media_type_changed", "warning", item.index, target.index)
        if item.length != target.length:
            finding("enclosure_length_changed", "warning", item.index, target.index)
        for field, code in (
            ("season", "season_changed"),
            ("number", "episode_number_changed"),
            ("kind", "episode_type_changed"),
        ):
            before, after = getattr(item, field), getattr(target, field)
            if before != after:
                finding(code, "error" if before is not None else "info", item.index, target.index)
        if item.permalink != target.permalink:
            finding("guid_permalink_changed", "warning", item.index, target.index)
        if _date(item.published) != _date(target.published):
            finding("pubdate_changed", "warning", item.index, target.index)
    for item in old.episodes:
        if item.index not in used_old:
            finding("unmatched_old_item", "error", item.index)
    for item in new.episodes:
        if item.index not in used_new:
            finding("unmatched_target_item", "info", new_item=item.index)
    pairs.sort(key=lambda pair: pair[0].index)
    matches = [
        {
            "old_item": left.index,
            "new_item": right.index,
            "basis": basis,
            "identity_preserved": preserved,
        }
        for left, right, basis, preserved in pairs[: limits.max_matches]
    ]
    return {
        "schema": SCHEMA,
        "passed": counts["error"] == 0 and (not strict or counts["warning"] == 0),
        "strict": strict,
        "allow_enclosure_identity": allow_enclosure_identity,
        "old_items": len(old.episodes),
        "new_items": len(new.episodes),
        "matched_items": len(pairs),
        "preserved_identities": sum(pair[3] for pair in pairs),
        "unmatched_old_items": len(old.episodes) - len(used_old),
        "unmatched_target_items": len(new.episodes) - len(used_new),
        "counts": {severity: counts[severity] for severity in ("error", "warning", "info")},
        "findings": findings,
        "findings_truncated": sum(counts.values()) > len(findings),
        "matches": matches,
        "matches_truncated": len(pairs) > len(matches),
    }
