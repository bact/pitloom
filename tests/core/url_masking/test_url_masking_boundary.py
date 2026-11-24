# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Where a credential found by its shape may start
(:mod:`pitloom.core.url_masking._boundary`): right after an escape sequence
the escaper wrote, not glued to plain letters.

See also: test_url_masking_tokens.py (the token shapes) and
test_url_masking_auth_schemes.py (``Bearer``, ``Basic``) in this folder.
"""

from __future__ import annotations

import re

import pytest

from pitloom.core.untrusted_text import DISPLAY_CONTROLS
from pitloom.core.url_masking import find_url_credentials, masked_given_path
from pitloom.core.url_masking._boundary import AFTER_ESCAPE
from pitloom.log_masking import masked_text
from pitloom.logging_config import loggable
from tests.core.url_masking._probe_corpus import TOKENS

#: A character of each escape spelling ``ascii()`` writes: ``\\t``, ``\\n``,
#: ``\\r``, ``\\xHH``, ``\\uHHHH`` and ``\\UHHHHHHHH``.
_CONTROLS = ("\t", "\n", "\r", "\x1b", "\x7f", "\u202e", "\U000e0001")
_CONTROL_IDS = ("tab", "lf", "cr", "esc", "del", "rlo", "tag")


def _escaped_forms(raw: str) -> tuple[str, str]:
    """*raw* as the escaper writes it, and that written again (each
    backslash doubled): both reach the masker from a call site."""
    once = loggable(raw)
    return once, loggable(once + "\n")


def test_every_escape_the_escaper_writes_is_a_boundary() -> None:
    """Each character ``loggable`` escapes, a control, a line or paragraph
    separator, a lone surrogate, a display control and a non-printable
    supplementary one, ends in an escape :data:`AFTER_ESCAPE` matches."""
    chars = [chr(code) for code in (*range(0x20), *range(0x7F, 0xA0))]
    chars += ["\u2028", "\u2029", "\ud800", "\U000e0001", *sorted(DISPLAY_CONTROLS)]
    for char in chars:
        inner = loggable(f"a{char}")[2:-1]
        assert inner != char, repr(char)
        assert re.search(f"(?:{AFTER_ESCAPE})\\Z", inner), inner


@pytest.mark.parametrize("prefix", list(TOKENS), ids=list(TOKENS))
def test_a_token_after_an_escape_is_masked(prefix: str) -> None:
    """A token of each shape right after each escape spelling, once and
    escaped again, is masked whole; so is one before it, as on the base
    tree."""
    token = prefix + TOKENS[prefix][0]
    for control in _CONTROLS:
        for raw in (f"remote: token:{control}{token}", f"{token}{control}x"):
            for escaped in _escaped_forms(raw):
                shown = masked_text(escaped)
                assert TOKENS[prefix][0] not in shown, (control, escaped)
                assert f"{prefix}***" in shown


@pytest.mark.parametrize(
    ("before", "masked"),
    [
        ("%20", True),
        (" ", True),
        ("\\t", True),
        ("\\\\n", True),
        ("\\x1b", True),
        ("\\xAB", True),
        ("\\u202e", True),
        ("\\U000e0001", True),
        ("ab", False),
        ("abt", False),
        ("\\q", False),
        ("\\x1", False),
        ("\\u202", False),
        ("\\U000e000", False),
        ("x1b", False),
        ("_", False),
    ],
    ids=[
        "pct",
        "space",
        "tab",
        "doubled-lf",
        "hex",
        "hex-upper",
        "u4",
        "u8",
        "letters",
        "t-glued",
        "not-escape",
        "short-x",
        "short-u",
        "short-uu",
        "no-backslash",
        "underscore",
    ],
)
def test_a_token_starts_after_an_escape_not_after_letters(
    before: str, masked: bool
) -> None:
    """Only a whole escape sequence (or a non-word character, a ``%XX``)
    starts a token: a token glued to plain letters, to an incomplete escape
    or to a letter after a backslash that escapes nothing is none, in the
    masker and the detector alike."""
    body = TOKENS["ghp_"][0]
    text = f"x{before}ghp_{body}"
    assert (body not in masked_given_path(text)) is masked
    assert bool(find_url_credentials(f"https://h/{text}")) is masked


@pytest.mark.parametrize(
    "raw",
    [
        "x:\talice:pw99@host:o/r",
        "x:\x1bpkg:generic/a?download_url=https%3A%2F%2Fu%3AS3CRET%40h",
    ],
    ids=["scp", "purl"],
)
def test_an_scp_address_and_a_purl_after_an_escape_are_masked_as_raw(
    raw: str,
) -> None:
    """An scp-style address and a PURL right after an escape are masked as
    they are in the raw text: the password and the qualifier hidden alike."""
    escaped = loggable(raw)
    assert escaped != raw
    shown = masked_text(escaped)
    assert "pw99" not in shown and "S3CRET" not in shown
    assert shown == loggable(masked_text(raw))
