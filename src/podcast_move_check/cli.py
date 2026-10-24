"""Offline snapshot-only podcast migration gate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .core import InputError, compare_feeds, read_feed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check episode continuity between two local RSS 2.0 snapshots."
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("old_feed", type=Path)
    parser.add_argument("new_feed", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true", help="Fail on warnings as well as errors")
    parser.add_argument(
        "--allow-enclosure-identity",
        action="store_true",
        help="Explicitly accept legacy no-GUID identity by exact, unique enclosure URL",
    )
    args = parser.parse_args(argv)
    try:
        result = compare_feeds(
            read_feed(args.old_feed),
            read_feed(args.new_feed),
            strict=args.strict,
            allow_enclosure_identity=args.allow_enclosure_identity,
        )
    except (InputError, OSError, ValueError) as exc:
        error = {"passed": False, "error": f"Check incomplete: {exc}"}
        print(json.dumps(error, ensure_ascii=True), file=sys.stdout if args.json else sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    else:
        print(
            f"{'PASS' if result['passed'] else 'FAIL'}: "
            f"{result['preserved_identities']}/{result['old_items']} old identities preserved"
        )
        print(
            "Items are 1-based positions in each supplied snapshot. "
            "Identifiers and URLs are omitted."
        )
        for finding in result["findings"]:
            positions = ", ".join(
                f"{key}={finding[key]}" for key in ("old_item", "new_item") if key in finding
            )
            print(f"{finding['severity']}: {finding['code']} {positions}".rstrip())
        if result["findings_truncated"]:
            print(f"Findings truncated; totals: {json.dumps(result['counts'], sort_keys=True)}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
