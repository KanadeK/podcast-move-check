"""Require real pass/fail outcomes on original synthetic RSS snapshots."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".demo").resolve()
    root.mkdir(exist_ok=False)
    examples = Path(__file__).resolve().parent
    for name in ("old.xml", "migrated.xml", "broken.xml"):
        shutil.copyfile(examples / name, root / name)
    for name, expected in (("migrated.xml", 0), ("broken.xml", 1)):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "podcast_move_check",
                str(root / "old.xml"),
                str(root / name),
                "--json",
            ],
            check=False,
        )
        if result.returncode != expected:
            raise SystemExit(
                f"Unexpected exit for {name}: {result.returncode}; expected {expected}"
            )
    print("Demo verified: host move passed; changed GUID failed as expected.")


if __name__ == "__main__":
    main()
