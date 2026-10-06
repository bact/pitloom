# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Deviations the checks find that are already tracked in
``working-docs/design/roadmap.md`` (or a design doc an entry there links):
a failing check matching one of these
globs *with its tracked failure text* is reported as ``KNOWN``, with the
roadmap item, not ``FAIL``.

Remove an entry as soon as its roadmap item is done, so a regression
fails again. Never add one without a roadmap item to point to.
"""

from __future__ import annotations

import fnmatch

# Check-id glob -> (roadmap item, text the failure detail must contain).
# Both must match: any other failure in the same cell still FAILs.
KNOWN: dict[str, tuple[str, str]] = {
    "S2": (
        "Re-embedding lists the previous embedded SBOM",
        "re-embedding changed the SBOM",
    ),
}


def known_issue(check_id: str, detail: str) -> str | None:
    """The roadmap item tracking *check_id*'s failure, if *detail* is
    the tracked failure."""
    for pattern, (item, sign) in KNOWN.items():
        if fnmatch.fnmatchcase(check_id, pattern) and sign in detail:
            return f"roadmap: {item}"
    return None
