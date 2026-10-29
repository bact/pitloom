# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Sweep licenseid's 0.7.0 parity corpus through Pitloom's declared-licence path.

Reads ``tests/fixtures/resolver_parity.tsv`` of the licenseid repository (the
values, Pitloom 0.21.1's answer in ``pitloom_0_21_1`` and the answer the 0.7.0
plan expects in ``expected_0_7_0``), classifies every value with the installed
Pitloom, and prints how the installed answer, the recorded 0.21.1 answer and the
expected one relate. Run it before and after adopting a licenseid release; every
row listed as moved needs a reason in the adoption plan
(``working-docs/design/licenseid-0-7-adoption.md``).

Needs a licenseid database: ``HOME=$(mktemp -d) licenseid update --source
packaged`` builds one offline in a scratch home; run this script with the same
``HOME``. Usage: ``python scripts/licence_adoption_sweep.py PARITY.tsv``.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

from pitloom.extract._license_classify import classify_license

_EXPECTED_RE = re.compile(r"^(?P<expr>.*) \[(?P<category>\w+)\]$")


def _read(path: Path) -> list[dict[str, str]]:
    lines = [
        line.rstrip("\n")
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    header = lines[0].split("\t")
    return [dict(zip(header, line.split("\t"), strict=False)) for line in lines[1:]]


def _unescape(field: str) -> str:
    return field.encode("ascii", "backslashreplace").decode("unicode_escape")


def _expected(row: dict[str, str]) -> str | None:
    """The expression the plan expects, ``'?'`` when undecided, else ``None``."""
    text = row["expected_0_7_0"]
    if text == "=":
        text = row["expression_0_6_0"]
        return None if text == "-" else text
    if text == "?":
        return "?"
    match = _EXPECTED_RE.match(text)
    return match.group("expr") if match and not text.startswith("- [") else None


def _now(value: str) -> str:
    classified = classify_license(value, warn=False)
    if classified is None or classified.kind == "text":
        return "text:"
    return f"{classified.kind}:{classified.value}"


def main(argv: list[str] | None = None) -> int:
    """Print the sweep; exit 1 when the installed answer drifts from 0.21.1's."""
    parser = argparse.ArgumentParser(
        description=(__doc__ or "").split("\n\n", maxsplit=1)[0]
    )
    parser.add_argument("parity", type=Path, help="licenseid resolver_parity.tsv")
    args = parser.parse_args(argv)
    counts: Counter[str] = Counter()
    for row in _read(args.parity):
        value = _unescape(row["value"])
        recorded, now = row["pitloom_0_21_1"], _now(value)
        expected = _expected(row)
        read = now.startswith("expression:")
        target = now.partition(":")[2] if read else None
        if now != recorded:
            kind = "DRIFT (installed differs from the recorded 0.21.1 answer)"
        elif expected == "?":
            kind = "undecided in the plan"
        elif target == expected:
            kind = "same"
        elif read and expected:
            kind = "moves: another expression"
        elif read:
            kind = "moves: read now, refused by the plan"
        else:
            kind = "moves: text now, read by the plan"
        counts[kind] += 1
        if kind != "same":
            print(f"{kind}\t{value!r}\tnow={now}\tplan={row['expected_0_7_0']}")
    print(file=sys.stderr)
    for kind, number in sorted(counts.items()):
        print(f"INFO: {number:4d} {kind}", file=sys.stderr)
    return 1 if any(key.startswith("DRIFT") for key in counts) else 0


if __name__ == "__main__":
    sys.exit(main())
