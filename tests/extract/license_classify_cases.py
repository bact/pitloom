# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The value table of :func:`pitloom.extract._license_classify.classify_license`
tests: the early exits Pitloom keeps (no licence, ``NOASSERTION``, ``NONE``,
long and multi-line text) and the mainstream answers of LicenseID, which
reads every expression. Edge answers LicenseID may still move (the order
of a reference beside an id, quotes, end marks) are not pinned here.

See also: tests/extract/test_license_classify.py,
tests/extract/test_license_classify_parsing.py,
tests/extract/test_license_readback_guard.py.
"""

from __future__ import annotations

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
    # valid SPDX with a ``+`` or an ``AdditionRef-``: canonical like any other
    ("Apache-2.0+", "expression", "Apache-2.0+", False),
    ("apache-2.0+", "expression", "Apache-2.0+", False),
    # repeated terms collapse only when identical
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
    # a deprecated ``+`` id is its listed successor
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
    # `+` only follows a listed licence id
    ("LicenseRef-foo+", "text", "LicenseRef-foo+", False),
    ("DocumentRef-x:LicenseRef-y+", "text", "DocumentRef-x:LicenseRef-y+", False),
    ("MIT WITH AdditionRef-x+", "text", "MIT WITH AdditionRef-x+", True),
    ("GPLv3 +", "text", "GPLv3 +", False),  # a plus after a space: refused
    ("GPL-2.0++", "text", "GPL-2.0++", False),
    ("LGPL-2.1++", "text", "LGPL-2.1++", False),
    ("GPL-2.0-only+", "text", "GPL-2.0-only+", False),
    ("GPL-2.0-or-later+", "text", "GPL-2.0-or-later+", False),
    ("licenseref-foo", "expression", "LicenseRef-foo", False),
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
    # re-spelt by LicenseID (said at INFO, not WARNING)
    ("Apache2", "expression", "Apache-2.0", False),
    ("MIT License", "expression", "MIT", False),
    ("Apache2 OR MIT", "expression", "Apache-2.0 OR MIT", False),
    ("GPLv3", "expression", "GPL-3.0", False),  # its -only/-or-later unknown
    ("BSD 3-Clause License", "expression", "BSD-3-Clause", False),  # prose
    ("MIT or later", "expression", "MIT+", False),  # a stated "or later"
    # a dash or no-break space before "or later" is still the grant
    ("GPL-2.0 - or later", "expression", "GPL-2.0-or-later", False),
    ("GPL-2.0 \u2013 or later", "expression", "GPL-2.0-or-later", False),
    ("GPL-2.0\u00a0or later", "expression", "GPL-2.0-or-later", False),
    ("LGPL-2.1 - or later", "expression", "LGPL-2.1-or-later", False),
    ("StandardML-NJ", "expression", "SMLNJ", False),  # renamed on the List
    # licences joined by a semicolon name no operator: text, not a guess
    ("MIT; Apache-2.0", "text", "MIT; Apache-2.0", False),
    # text, silent
    (" Foo ", "text", "Foo", False),
    ("Foo AND Bar", "text", "Foo AND Bar", False),
    ("Classpath-exception-2.0", "text", "Classpath-exception-2.0", False),
    ("Apache\x1f2.0", "text", "Apache\x1f2.0", False),  # a control character
    ("MIT\nApache-2.0", "text", "MIT\nApache-2.0", False),
    ("MIT OR\nApache-2.0", "text", "MIT OR\nApache-2.0", False),  # never parsed
    (LONG_BODY, "text", LONG_BODY.strip(), False),
    # the length boundary: 200 parses, 201 does not
    (padded(200), "expression", "MIT", False),
    (padded(201), "text", padded(201), False),
]
