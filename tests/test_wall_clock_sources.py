# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""No wall-clock read reaches the output except as the last fallback.

Output must be byte-identical across runs once a datetime is pinned
(``--creation-datetime``, ``[tool.pitloom] creation-datetime`` or
``SOURCE_DATE_EPOCH``). A wall-clock read is allowed only where it is the
last step of that cascade, listed below with its reason. A new one -- such
as the enrichment ``CreationInfo`` that once read the clock directly, and
made two runs a second apart differ -- fails here: route it through the
pinned value instead, or add it with the reason it cannot leak.

See also: :mod:`tests.assemble.test_enrichment_created`.
"""

from __future__ import annotations

import re
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src" / "pitloom"
_WALL_CLOCK = re.compile(
    r"\bdatetime\.(?:now|utcnow|today)\(|\btime\.time(?:_ns)?\(|\bdate\.today\("
)

#: File (relative to ``src/pitloom``) -> number of wall-clock reads, each
#: the last fallback after the pinned sources.
_ALLOWED = {
    # spdx3_utc_now(): the fallback of resolve_creation_datetime-style
    # cascades; callers try the pin and SOURCE_DATE_EPOCH first.
    "assemble/spdx3/creation_info.py": 1,
    # ZIP entry time when neither the SBOM datetime nor an epoch is set.
    "_embed_wheel.py": 1,
    # Hatchling hook: after creation-datetime and SOURCE_DATE_EPOCH.
    "plugins/hatch.py": 1,
}


def _reads() -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in sorted(_SRC.rglob("*.py")):
        code = "\n".join(
            line.split("#", 1)[0]
            for line in path.read_text(encoding="utf-8").splitlines()
        )
        found = len(_WALL_CLOCK.findall(code))
        if found:
            counts[path.relative_to(_SRC).as_posix()] = found
    return counts


def test_wall_clock_is_read_only_as_the_last_fallback() -> None:
    assert _reads() == _ALLOWED


def test_the_scan_sees_a_wall_clock_read() -> None:
    """Non-vacuous: the pattern matches the spellings it is meant to."""
    for code in (
        "datetime.now(timezone.utc)",
        "datetime.utcnow()",
        "time.time()",
        "date.today()",
    ):
        assert _WALL_CLOCK.search(code), code
    assert not _WALL_CLOCK.search("to_spdx3_datetime(created)")


_RAW_PARSE = re.compile(r"\.fromisoformat\(|\.strptime\(")


def test_datetime_strings_are_parsed_only_by_parse_iso_datetime() -> None:
    """A raw ``fromisoformat()`` rejects ``Z`` on Python 3.10 and keeps an
    offset as given; ``parse_iso_datetime()`` (then ``to_spdx3_datetime()``)
    is the one parse that gives an SPDX 3 DateTime. ``builtTime`` once used a
    raw parse and failed the Hatchling build on 3.10."""
    found: dict[str, int] = {}
    for path in sorted(_SRC.rglob("*.py")):
        code = "\n".join(
            line.split("#", 1)[0]
            for line in path.read_text(encoding="utf-8").splitlines()
        )
        if count := len(_RAW_PARSE.findall(code)):
            found[path.relative_to(_SRC).as_posix()] = count
    assert found == {"assemble/spdx3/creation_info.py": 1}
    for code in (
        "datetime.fromisoformat(s)",
        "date.fromisoformat(s)",
        "dt.fromisoformat(s)",
        "datetime.strptime(s, f)",
    ):
        assert _RAW_PARSE.search(code), code
