# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Id counters of a Loom ID registry: a retired id is never minted again.

For each id prefix (``File``, ``Package``, ...) a registry keeps the
highest number it has minted or seen in its namespace. A mint takes one
more, so an id that left the table (a harvest replaced its entry) is not
handed to another key. Counters only grow: two tables merge by maximum.

See also: :mod:`pitloom.id_registry._registry` (``IdRegistry`` mints and
reserves), :mod:`pitloom.id_registry._format` (stored as ``id_counters``).
"""

from __future__ import annotations

import re

from pitloom.core.canonical_json import MAX_SAFE_INTEGER
from pitloom.core.iri import is_iri_segment

__all__ = [
    "MAX_ID_NUMBER",
    "RESERVE_CEILING",
    "Counters",
    "id_number",
    "merge_counters",
]

#: The largest counter: RFC 8785 writes a larger integer as a string, which
#: would not load back.
MAX_ID_NUMBER = MAX_SAFE_INTEGER

#: The largest number an id read from an SBOM or a table reserves. A foreign
#: source can hand over any number up to :data:`MAX_ID_NUMBER`; reserving it
#: would leave no number to mint. 10**9 is far above any project's mint
#: count and leaves almost all of the range to mints.
RESERVE_CEILING = 10**9

#: Id prefix -> the highest number minted or seen under it.
Counters = dict[str, int]

# A number as a mint writes it: ASCII digits, no leading zero, and at most
# as many digits as MAX_ID_NUMBER, so int() never meets a long string.
_NUMBER = re.compile(r"[1-9][0-9]{0,15}")


def id_number(namespace: str, spdx_id: str) -> tuple[str, int] | None:
    """``(prefix, n)`` when *spdx_id* is ``<namespace>#<prefix>-<n>``, the
    shape a mint writes: *prefix* an id prefix a counter can be stored
    under (:func:`~pitloom.core.iri.is_iri_segment`, as a mint encodes it)
    and *n* from 1 to :data:`MAX_ID_NUMBER`. Else ``None``: another
    namespace, a fragment such as ``AIPackage-whisper-tiny`` that ends in
    no number, or a prefix no mint writes (``pkg/requests``), which can
    never collide with a minted id."""
    head = namespace + "#"
    if not spdx_id.startswith(head):
        return None
    prefix, _, digits = spdx_id[len(head) :].rpartition("-")
    if not is_iri_segment(prefix) or not _NUMBER.fullmatch(digits):
        return None
    number = int(digits)
    return (prefix, number) if number <= MAX_ID_NUMBER else None


def merge_counters(first: Counters, second: Counters) -> Counters:
    """Each prefix of *first* and *second* at the larger of its two values."""
    return {
        prefix: max(first.get(prefix, 0), second.get(prefix, 0))
        for prefix in sorted(first.keys() | second.keys())
    }
