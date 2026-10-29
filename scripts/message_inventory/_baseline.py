# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The ratchet baseline: how many uncoded in-scope sites each module has, one
``module count`` line per module with at least one, sorted by module.

The counts may only fall, per module and in total. A rise is a new uncoded
message (give it a code); a fall must be written down by regenerating the
baseline, so the gain cannot be lost again. Regenerating writes falls only:
it refuses while a module or the total is above the baseline, so a site that
moves to another module is moved in the file by hand, and the total holds
the sum.

See also: ``_scope.py`` (what counts) and ``tests/test_message_ratchet.py``.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from ._scope import in_scope

#: The baseline, relative to the repository root.
BASELINE_PATH = Path("tests/fixtures/message-inventory/uncoded.txt")
#: How to regenerate it (also written into its header).
REGENERATE = "python -m scripts.message_inventory --write-baseline"


def uncoded_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    """In-scope sites without a code, by module name."""
    counts = Counter(
        rec["module"] for rec in records if in_scope(rec) and not rec["coded"]
    )
    return dict(sorted(counts.items()))


def format_baseline(counts: dict[str, int]) -> str:
    """The baseline file text (LF line ends, sorted, no timestamp)."""
    header = [
        "# Uncoded message sites per module: the ratchet baseline of",
        "# tests/test_message_ratchet.py. A count may fall, never rise.",
        "# Format: <module> <count>. A module with no uncoded site is absent.",
        f"# Regenerate from the repository root: {REGENERATE}",
    ]
    body = [f"{module} {count}" for module, count in sorted(counts.items())]
    return "\n".join(header + body) + "\n"


def parse_baseline(text: str) -> dict[str, int]:
    """The counts in a baseline text.

    Raises:
        ValueError: A line is not ``<module> <count>``.
    """
    counts: dict[str, int] = {}
    for no, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        fields = line.split(" ")
        if len(fields) != 2 or not fields[1].isdigit() or fields[0] in counts:
            raise ValueError(f"baseline line {no}: expected '<module> <count>'")
        counts[fields[0]] = int(fields[1])
    return counts


#: What a rise asks for.
_RISE = "a new message needs a code (pitloom.messages); do not raise the baseline"


def rises(baseline: dict[str, int], current: dict[str, int]) -> list[str]:
    """The rises of *current* over *baseline*, one line each: each module
    above its count, sorted, then the total when it is above the baseline's
    (a site moved to another module counts once)."""
    problems = [
        f"{module}: {current[module]} uncoded message sites, baseline "
        f"{baseline.get(module, 0)}: {_RISE}"
        for module in sorted(current)
        if current[module] > baseline.get(module, 0)
    ]
    was, now = sum(baseline.values()), sum(current.values())
    if now > was:
        problems.append(f"total: {now} uncoded message sites, baseline {was}: {_RISE}")
    return problems


def compare(baseline: dict[str, int], current: dict[str, int]) -> list[str]:
    """The problems of *current* against *baseline*, one line each: the
    rises (:func:`rises`), then each fall (a stale baseline), by module."""
    problems = rises(baseline, current)
    for module in sorted(set(baseline) | set(current)):
        was, now = baseline.get(module, 0), current.get(module, 0)
        if now < was:
            problems.append(
                f"{module}: {now} uncoded message sites, baseline {was}: lower "
                f"the baseline with '{REGENERATE}'"
            )
    return problems
