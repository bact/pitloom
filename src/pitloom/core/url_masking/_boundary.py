# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Where a credential found by its shape may start: not glued to the word
before it, but right after an escape sequence.

See also: :mod:`pitloom.core.url_masking._tokens` (an access token),
:mod:`pitloom.core.url_masking._userinfo` (an scp-style address),
:mod:`pitloom.core.url_masking._mask` (a PURL) and
:mod:`pitloom.core.url_masking._auth_schemes` (``Bearer``, ``Basic``), the
patterns that start so. Standard library only.

A text often reaches the masker escaped already: a call site writes a name
through :func:`pitloom.logging_config.loggable` and the log formatter masks
the line. Python's ``ascii()``, the escaper behind it, writes a tab as
``\\t`` and an escape character as ``\\x1b``: the last character of the
escape is a letter or a hexadecimal digit, which reads as the end of a word
glued to the credential (``token:\\tghp_...``). So a credential directly
after one of the escapes ``ascii()`` writes for a character it does not
print, ``\\t``, ``\\n``, ``\\r``, ``\\xHH``, ``\\uHHHH`` and ``\\UHHHHHHHH``
(``H`` a hexadecimal digit of either case), starts there, as after
white space; also in the doubled form an escape takes when its text is
escaped again (``\\\\t``). A credential glued to plain letters does not
(``abtghp_...``). The text cannot tell an escape from a backslash typed
before a letter (a Windows path ``C:\\tghp_...``, a folder ``tghp_...``):
that is read as an escape too, so the name after it may be masked.
"""

from __future__ import annotations

__all__ = ["AFTER_ESCAPE", "word_start"]

#: Right after an escape sequence ``ascii()`` writes, as a regular
#: expression: one fixed-width lookbehind per length, so the check costs
#: the same at each position.
AFTER_ESCAPE = "|".join(
    (
        r"(?<=\\[tnr])",
        r"(?<=\\x[0-9A-Fa-f]{2})",
        r"(?<=\\u[0-9A-Fa-f]{4})",
        r"(?<=\\U[0-9A-Fa-f]{8})",
    )
)


def word_start(glued: str, *also: str) -> str:
    """A regular expression matching where a credential may start: not
    after a character of the class *glued* (written as inside ``[]``), or
    right after an escape sequence (:data:`AFTER_ESCAPE`), or after any of
    the further lookbehinds *also*."""
    return "(?:" + "|".join((f"(?<![{glued}])", *also, AFTER_ESCAPE)) + ")"
