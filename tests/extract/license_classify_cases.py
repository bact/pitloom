# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The value table of :func:`pitloom.extract._license_classify.classify_license`
tests, shared by the tests that stay with it and the ones that go with
Pitloom's own expression parsing.

A value that has an operator (``AND``, ``OR``, ``WITH``), a ``+``, an
``AdditionRef-`` or a gap placeholder depends on that parsing: its expected
answer (order of operands, the gap spellings) is what ``licenseid`` 0.7.0 takes
over, so the table is regenerated from the adoption sweep when Pitloom adopts it.
Every other value stays as it is.

See also: tests/extract/test_license_classify.py,
tests/extract/test_license_classify_parsing.py,
tests/extract/test_license_parse_drift_guard.py.
"""

from __future__ import annotations

import re

LONG_BODY = "Permission is granted to use, copy and modify this software, and " * 800


def padded(length: int) -> str:
    """A valid expression of exactly *length* characters."""
    text = f"MIT{' ' * (length - 9)}OR MIT"
    assert len(text) == length
    return text


#: (raw, kind, value, whether a WARNING is expected); ``None`` kind = no licence.
CASES = [
    # no licence stated
    (None, None, "", False),
    ("", None, "", False),
    ("  \t ", None, "", False),
    # UNKNOWN: the source does not know, which is NOASSERTION
    ("UNKNOWN", "noassertion", "NOASSERTION", False),
    ("unknown", "noassertion", "NOASSERTION", False),
    (" Unknown ", "noassertion", "NOASSERTION", False),
    # individuals, in any case
    ("NOASSERTION", "noassertion", "NOASSERTION", False),
    (" noassertion ", "noassertion", "NOASSERTION", False),
    ("NONE", "none", "NONE", False),
    ("none", "none", "NONE", False),
    # valid expressions, canonical
    ("MIT", "expression", "MIT", False),
    ("mit", "expression", "MIT", False),
    ("mit and apache-2.0", "expression", "Apache-2.0 AND MIT", False),
    (
        "MIT AND (Apache-2.0 OR GPL-2.0-only)",
        "expression",
        "MIT AND (Apache-2.0 OR GPL-2.0-only)",
        False,
    ),
    (
        "GPL-2.0-only WITH Classpath-exception-2.0",
        "expression",
        "GPL-2.0-only WITH Classpath-exception-2.0",
        False,
    ),
    ("LicenseRef-foo", "expression", "LicenseRef-foo", False),
    ("bsd-3-clause", "expression", "BSD-3-Clause", False),
    ("GPL-2.0-OR-LATER", "expression", "GPL-2.0-or-later", False),
    ("MIT AND MIT", "expression", "MIT", False),
    ("(mit and mit)", "expression", "MIT", False),
    ("(MIT)", "expression", "MIT", False),
    # operator words glued into an id are not operators
    ("LicenseRef-my-or-license", "expression", "LicenseRef-my-or-license", False),
    ("LicenseRef-and-tool", "expression", "LicenseRef-and-tool", False),
    # grammar gaps: canonical like any expression
    ("Apache-2.0+", "expression", "Apache-2.0+", False),
    ("apache-2.0+", "expression", "Apache-2.0+", False),
    # grammar-gap terms collapse only when identical
    ("MIT+ OR MIT+", "expression", "MIT+", False),
    (
        "Apache-2.0+  WITH  AdditionRef-x",
        "expression",
        "Apache-2.0+ WITH AdditionRef-x",
        False,
    ),
    (
        "Apache-2.0 WITH AdditionRef-x OR MIT",
        "expression",
        "MIT OR Apache-2.0 WITH AdditionRef-x",
        False,
    ),
    ("MIT+ OR MIT", "expression", "MIT OR MIT+", False),  # distinct terms
    (
        "apache-2.0+ with classpath-exception-2.0",
        "expression",
        "Apache-2.0+ WITH Classpath-exception-2.0",
        False,
    ),
    # a deprecated id with a listed successor is replaced by it
    ("GPL-2.0+", "expression", "GPL-2.0-or-later", False),
    ("lgpl-2.1+", "expression", "LGPL-2.1-or-later", False),
    ("gpl-2.0+ or mit", "expression", "GPL-2.0-or-later OR MIT", False),
    (
        "GPL-2.0+ WITH Classpath-exception-2.0",
        "expression",
        "GPL-2.0-or-later WITH Classpath-exception-2.0",
        False,
    ),
    (
        "Apache-2.0 WITH AdditionRef-x",
        "expression",
        "Apache-2.0 WITH AdditionRef-x",
        False,
    ),
    ("GPL-2.0", "expression", "GPL-2.0", False),
    # an addition after an id that says only/or-later, or a user reference
    (
        "GPL-2.0-only WITH AdditionRef-x",
        "expression",
        "GPL-2.0-only WITH AdditionRef-x",
        False,
    ),
    (
        "LicenseRef-a WITH AdditionRef-x",
        "expression",
        "LicenseRef-a WITH AdditionRef-x",
        False,
    ),
    (
        "DocumentRef-d:LicenseRef-a WITH AdditionRef-x",
        "expression",
        "DocumentRef-d:LicenseRef-a WITH AdditionRef-x",
        False,
    ),
    # a user's own reference spelled like the gap placeholder is kept
    (
        "LicenseRef-pitloom-gap-000 OR Apache-2.0+",
        "expression",
        "LicenseRef-pitloom-gap-000 OR Apache-2.0+",
        False,
    ),
    (
        "LicenseRef-pitloom-gap-0001 OR Apache-2.0+ OR MIT+",
        "expression",
        "LicenseRef-pitloom-gap-0001 OR Apache-2.0+ OR MIT+",
        False,
    ),
    # `+` only follows a listed licence id
    ("LicenseRef-foo+", "text", "LicenseRef-foo+", False),
    ("DocumentRef-x:LicenseRef-y+", "text", "DocumentRef-x:LicenseRef-y+", False),
    ("MIT WITH AdditionRef-x+", "text", "MIT WITH AdditionRef-x+", True),
    ("GPL-2.0++", "text", "GPL-2.0++", False),
    ("LGPL-2.1++", "text", "LGPL-2.1++", False),
    ("GPL-2.0-only+", "text", "GPL-2.0-only+", False),
    ("GPL-2.0-or-later+", "text", "GPL-2.0-or-later+", False),
    ("licenseref-foo", "text", "licenseref-foo", False),
    # an addition needs a licence: a listed id or a well-formed reference
    ("Foo WITH AdditionRef-x", "text", "Foo WITH AdditionRef-x", False),
    ("LicenseRef- WITH AdditionRef-x", "text", "LicenseRef- WITH AdditionRef-x", False),
    (
        "LicenseRef-a+ WITH AdditionRef-x",
        "text",
        "LicenseRef-a+ WITH AdditionRef-x",
        True,
    ),
    # looks like an expression, is not: text and one WARNING
    ("GPL-2.0+ OR Foo", "text", "GPL-2.0+ OR Foo", True),
    ("(GPL-2.0+", "text", "(GPL-2.0+", True),
    ("GPL-2.0+ AND", "text", "GPL-2.0+ AND", True),
    ("mit or", "text", "mit or", True),
    ("MIT with attribution", "text", "MIT with attribution", True),
    ("MIT OR", "text", "MIT OR", True),
    ("(MIT", "text", "(MIT", True),
    ("MIT)", "text", "MIT)", True),
    ("GPL-2.0-only+ OR Foo", "text", "GPL-2.0-only+ OR Foo", True),
    ("MIT AND Foo", "text", "MIT AND Foo", True),
    (
        "Apache-2.0 WITH AdditionRef-x AND Foo",
        "text",
        "Apache-2.0 WITH AdditionRef-x AND Foo",
        True,
    ),
    # read by licenseid as one licence (said at INFO, not WARNING)
    ("Apache2", "expression", "Apache-2.0", False),
    ("MIT License", "expression", "MIT", False),
    # text, silent
    (" Foo ", "text", "Foo", False),
    ("Foo AND Bar", "text", "Foo AND Bar", False),
    ("Classpath-exception-2.0", "text", "Classpath-exception-2.0", False),
    ("MIT\nApache-2.0", "text", "MIT\nApache-2.0", False),
    ("MIT OR\nApache-2.0", "text", "MIT OR\nApache-2.0", False),  # never parsed
    (LONG_BODY, "text", LONG_BODY.strip(), False),
    # the length boundary: 200 parses, 201 does not
    (padded(200), "expression", "MIT", False),
    (padded(201), "text", padded(201), False),
]


#: A value that Pitloom's own expression parsing decides (see the module doc).
_PARSING = re.compile(
    r"\+|AdditionRef|pitloom-gap|\s(?:AND|OR|WITH)(?:\s|$)", re.IGNORECASE
)
#: Multi-line and over-long values are text before any parser is asked.
_NEVER_PARSED = re.compile(r"[\r\n]")


def depends_on_parsing(raw: str | None) -> bool:
    """Whether the answer for *raw* is Pitloom's own expression parsing."""
    return (
        raw is not None
        and _NEVER_PARSED.search(raw) is None
        and len(raw) <= 200
        and _PARSING.search(raw) is not None
    )


STAYING = [case for case in CASES if not depends_on_parsing(case[0])]
PARSING = [case for case in CASES if depends_on_parsing(case[0])]
