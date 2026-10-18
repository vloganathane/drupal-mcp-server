#!/usr/bin/env python3
"""Compare a fresh full sweep against the committed baseline.

    python tests/live/compare_sweeps.py tests/live/sweep-results-ddev.json \\
        tests/live/sweep-results.json

The gate exists so a fresh run cannot silently ship a broken tool or a
behaviour change: DEAD is always fatal, and a tool the baseline had
passing (OK) that now comes back REJECTED or UPSTREAM has changed
semantics, not merely speed.

Timing is not semantics: OK -> BLOCKED is reported as a warning by
default, because a busy runner turns slow tools into timeouts without
anything being wrong with the tool. --strict makes those fatal too.

A tool named in --allow never fails the run. Use it only for verdicts
that legitimately differ between a pristine CI site and a long-lived
local one (a fixture the local site accumulated along the way), never to
wave through a real break - every entry deserves a comment wherever it
is recorded.

A missing baseline file is fatal: the comparison is the point of the
run. A missing actual file exits 0 with a loud notice, because that
means an earlier setup step already failed the job and this script
should not bury that cause under a second, vaguer error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Verdicts that mean the tool stopped working when the baseline had it
# working: a refusal or an upstream block on a call that used to succeed.
SEMANTIC = {"REJECTED", "UPSTREAM"}
# Verdicts that only say the run was slow or incomplete.
TIMING = {"BLOCKED", "SKIPPED"}


def load(path: Path) -> dict[str, str]:
    records = json.loads(path.read_text())
    return {r["tool"]: r["verdict"] for r in records}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("actual", type=Path)
    parser.add_argument(
        "--strict", action="store_true",
        help="treat timing verdicts (BLOCKED/SKIPPED) as failures too",
    )
    parser.add_argument(
        "--allow", default="",
        help="comma-separated tools exempt from failure (fresh-vs-local site "
             "differences only)",
    )
    args = parser.parse_args()
    allowed = {t.strip() for t in args.allow.split(",") if t.strip()}

    if not args.actual.exists():
        print(f"NOTICE: no sweep results at {args.actual} - the sweep never "
              f"ran; the earlier step already failed this job.")
        return 0
    if not args.baseline.exists():
        print(f"FATAL: baseline {args.baseline} does not exist - nothing to "
              f"compare against, and inventing one would defeat the gate.")
        return 1

    baseline = load(args.baseline)
    actual = load(args.actual)

    fatal: list[str] = []
    warned: list[str] = []
    improved: list[str] = []
    washed: list[str] = []

    for tool, after in sorted(actual.items()):
        before = baseline.get(tool)
        if before is None:
            washed.append(f"{tool}: not in baseline ({after}) - new tool?")
            continue
        if after == before:
            continue
        note = f"{tool}: {before} -> {after}"
        if tool in allowed:
            washed.append(note + " (allowed)")
        elif after == "DEAD":
            fatal.append(note + " - the tool is broken")
        elif before == "OK" and after in SEMANTIC:
            fatal.append(note + " - passed in baseline, now refuses")
        elif before == "OK" and after in TIMING:
            (fatal if args.strict else warned).append(note + " - timing only")
        elif after == "OK":
            improved.append(note + " - now passing")
        else:
            washed.append(note)

    for tool in baseline:
        if tool not in actual:
            fatal.append(f"{tool}: in baseline but never swept this run")

    print("=" * 60)
    print(f"compare: {args.actual.name} vs {args.baseline.name}")
    print(f"  {len(actual)} tools swept, "
          f"{sum(1 for v in actual.values() if v == 'OK')} OK "
          f"(baseline: {sum(1 for v in baseline.values() if v == 'OK')} OK)")
    for title, items in (("FATAL", fatal), ("WARNINGS", warned),
                         ("IMPROVEMENTS", improved), ("CHANGED", washed)):
        if items:
            print(f"\n{title} ({len(items)}):")
            for line in items:
                print(f"  {line}")

    if fatal:
        print(f"\nFAIL: {len(fatal)} regression(s)")
        return 1
    if warned:
        print(f"\n{'FAIL' if args.strict else 'PASS'}: "
              f"{len(warned)} timing warning(s)")
        return 1 if args.strict else 0
    print("\nPASS: no regressions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
