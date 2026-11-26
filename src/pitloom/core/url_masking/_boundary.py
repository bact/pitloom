# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Where a credential found by its shape may start: not glued to the word
before it, but right after an escape sequence or a terminal colour
sequence.

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

A build's or a tool's coloured output glues a credential to the last
letter of an ANSI CSI sequence (``token: \\x1b[33mghp_...``, ``m`` its last
letter). So a credential also starts right after such a sequence: ``ESC [``,
at most :data:`_CSI_PARAMS` parameter characters (ECMA-48: digits and
``:;<=>?``) and a final letter (``\\x1b[m``, ``\\x1b[1;33m``,
``\\x1b[38:5:196m``, ``\\x1b[K``, ``\\x1b[?25l``), the escape character
raw or written ``\\x1b`` by ``ascii()``, once or doubled. A sequence of
more parameter characters is no boundary, so the credential after it is
missed; so is one after an OSC or another non-CSI sequence. Letters glued
without the escape character (``2mghp_...``, ``x[33mghp_...``) are a word,
as above.
"""

from __future__ import annotations

__all__ = ["AFTER_ANSI", "AFTER_ESCAPE", "CSI", "word_start"]

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

#: The most parameter characters of an ANSI CSI sequence read as a boundary.
_CSI_PARAMS = 16
#: The escape character before ``[`` of a CSI sequence, as a regular
#: expression: raw, or written ``\\x1b`` by ``ascii()`` (the doubled form
#: ``\\\\x1b`` ends with it).
_ESC_FORMS = (r"\x1b", r"\\x1b")
#: A parameter character of a CSI sequence (ECMA-48: ``0x30`` to ``0x3F``).
_CSI_PARAM = "[0-?]"
#: An ANSI CSI sequence, the escape character raw or written by ``ascii()``
#: once or twice (``\\x1b``, ``\\\\x1b``), as a regular expression.
CSI = r"(?:\x1b|\\{1,2}x1b)\[" + _CSI_PARAM + f"{{0,{_CSI_PARAMS}}}[A-Za-z]"
#: Right after an ANSI CSI sequence (``\\x1b[33m``), as a regular expression:
#: one fixed-width lookbehind per escape form and parameter count, run only
#: where a CSI sequence could end (a parameter character or ``[``, then a
#: letter), so a run of letters costs one cheap check per position.
AFTER_ANSI = (
    r"(?<=[0-?\[][A-Za-z])(?:"
    + "|".join(
        rf"(?<={esc}\[{_CSI_PARAM}{{{count}}}[A-Za-z])"
        for count in range(_CSI_PARAMS + 1)
        for esc in _ESC_FORMS
    )
    + ")"
)


def word_start(glued: str, *also: str) -> str:
    """A regular expression matching where a credential may start: not
    after a character of the class *glued* (written as inside ``[]``), or
    right after an escape sequence (:data:`AFTER_ESCAPE`) or an ANSI CSI
    sequence (:data:`AFTER_ANSI`), or after any of the further lookbehinds
    *also*."""
    return "(?:" + "|".join((f"(?<![{glued}])", *also, AFTER_ESCAPE, AFTER_ANSI)) + ")"
