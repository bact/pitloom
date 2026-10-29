# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The message inventory: every place ``src/pitloom`` emits a message, and
whether it is *coded* (says a ``pitloom.messages`` message, so its line ends
in `` [code]``).

Static (``ast``); nothing is imported from Pitloom. From the repository root::

    python -m scripts.message_inventory                 # counts
    python -m scripts.message_inventory --check         # the ratchet
    python -m scripts.message_inventory --write-baseline
    python -m scripts.message_inventory --jsonl -       # every site
    python -m scripts.message_inventory --quotes -      # skill quotes

The ratchet baseline is ``tests/fixtures/message-inventory/uncoded.txt``;
``tests/test_message_ratchet.py`` runs it.

See also: ``working-docs/design/message-catalogue-and-skills.md``.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from ._baseline import (
    BASELINE_PATH,
    REGENERATE,
    compare,
    format_baseline,
    parse_baseline,
    rises,
    uncoded_counts,
)
from ._families import emitter_family
from ._quotes import collect_skill_quotes, match_quotes
from ._scope import in_scope
from ._walker import walk

__all__ = [
    "BASELINE_PATH",
    "REGENERATE",
    "collect_skill_quotes",
    "compare",
    "format_baseline",
    "in_scope",
    "inventory",
    "match_quotes",
    "parse_baseline",
    "rises",
    "summary",
    "uncoded_counts",
]


def inventory(root: Path) -> list[dict[str, Any]]:
    """Every emission site under ``root/src/pitloom``, sorted by file and
    line. Each record has ``module``, ``coded`` and the template fields."""
    return walk(root)


def summary(records: list[dict[str, Any]]) -> dict[str, int]:
    """Site counts: all, in scope, coded and uncoded among those in scope."""
    scoped = [rec for rec in records if in_scope(rec)]
    coded = sum(1 for rec in scoped if rec["coded"])
    return {
        "SITES": len(records),
        "CODED_SITES": sum(1 for rec in records if rec["coded"]),
        "IN_SCOPE": len(scoped),
        "IN_SCOPE_CODED": coded,
        "IN_SCOPE_UNCODED": len(scoped) - coded,
        "MODULES_UNCODED": len(uncoded_counts(records)),
    }


def families(records: list[dict[str, Any]]) -> dict[str, int]:
    """Site counts by emitter family."""
    return dict(sorted(Counter(emitter_family(r["emitter"]) for r in records).items()))
