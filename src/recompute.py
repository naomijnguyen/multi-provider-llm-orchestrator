"""Recompute the measures over an existing results CSV, in place.

    python -m src.recompute experiment/experiment_runs.csv [...]

METHODS.md §10 claims the raw response text is retained so that every measure
can be recomputed without re-running generation. This is the thing that makes
that claim true, and it is not hypothetical: the identity-claim detector missed
the "Grok here." byline form and scored a whole run as a null. Fixing the
measure and replaying it cost nothing, where re-generating would have cost the
run twice over.

Measures are recomputed; the response text, condition labels, and the
generation-time fields (finish_reason, thinking, is_error) are left alone —
those are facts about the API call and cannot be recovered from the text.
"""

from __future__ import annotations

import csv
import os
import sys

from .measures import measure


def recompute(path: str) -> tuple[int, int]:
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fields = reader.fieldnames or []
        rows = list(reader)

    changed = 0
    for row in rows:
        new = measure(row["response"], row["model"])
        # Only keys already in the file, so a CSV written by an older version
        # does not silently gain columns its header cannot hold.
        for k, v in new.items():
            if k != "is_error" and k in fields and str(v) != row[k]:
                row[k] = v
                changed += 1

    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)   # atomic: never leave a half-written results file
    return len(rows), changed


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for path in sys.argv[1:]:
        n, changed = recompute(path)
        print(f"{path}: {n} rows, {changed} cell(s) updated")


if __name__ == "__main__":
    main()
