# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The two values a ``wheel-sbom-conflict`` line compares (catalogue PR
16): masked whole before any cut, as an excerpt masks; shown so that two
different values never look alike (an escape against the character it
names, NFC against NFD, an astral character); a value not text shown
exactly as JSON.

See also: tests/messages/test_wheels_core_hostile.py (white space and
values that differ past the cut).
"""

from __future__ import annotations

import logging
import re
import unicodedata

import pytest

from pitloom.messages import MESSAGES, trusted_message
from pitloom.messages import wheel_sboms as s
from pitloom.messages._compared_value import (
    ComparedValue,
    compared_pair,
    compared_text,
)
from pitloom.messages._fields_lock import excerpt_text

pytestmark = pytest.mark.platform  # escapes and non-ASCII text in lines

_LOG = logging.getLogger("pitloom.core.wheel_dist_info")
_CODE = "wheel-sbom-conflict"
_SIDES = re.compile(r"SBOM name (.+) differs from the wheel's METADATA (.+)")


def _lines(caplog: pytest.LogCaptureFixture, wheel: str, sbom: str) -> list[str]:
    """The warning and the library error for one name mismatch, each
    checked to be one trusted line."""
    mismatch = s.IdentityMismatch("name", wheel, sbom)
    s.say_identity_mismatches(_LOG, "a.whl", [mismatch])
    exc = s.identity_mismatch_error(_LOG, "a.whl", [mismatch])
    (record,) = caplog.records
    caplog.clear()
    texts = [record.getMessage(), str(exc)]
    for text, level in zip(texts, ("WARNING", "ERROR"), strict=True):
        assert "\n" not in text and "\r" not in text
        assert trusted_message(f"{level}: {text} [{_CODE}]") is MESSAGES[_CODE]
    return texts


#: Secret-bearing pairs, each secret spelled ``SECRET``.
_SECRET_PAIRS = {
    "token-past-cut": (
        "a" * 115 + "?token=XSECRETpart",
        "a" * 115 + "?token=YSECRETpart",
    ),
    "token-in-name": ("pkg", "pkg?token=SECRET1"),
    "credential-before-difference": (
        "https://u:SECRET@h/" + "a" * 130 + "x",
        "https://u:SECRET@h/" + "a" * 130 + "y",
    ),
}


@pytest.mark.parametrize("swap", [False, True], ids=["wheel-sbom", "sbom-wheel"])
@pytest.mark.parametrize(
    ("wheel", "sbom"), _SECRET_PAIRS.values(), ids=list(_SECRET_PAIRS)
)
def test_a_secret_is_masked_before_any_cut(
    caplog: pytest.LogCaptureFixture, wheel: str, sbom: str, swap: bool
) -> None:
    if swap:
        wheel, sbom = sbom, wheel
    for text in _lines(caplog, wheel, sbom):
        assert "SECRET" not in text


#: Each credential shape an excerpt masks, the secret spelled ``SECRET``.
_MASKING_CORPUS = {
    "url-user-info": "see https://user:SECRET@host/path",
    "url-user-only": "https://SECRET@host/x",
    "query-token": "https://h/x?token=SECRET",
    "query-api-key": "https://h/x?a=1&api_key=SECRET",
    "free-param": "/x?access_token=SECRET",
    "free-param-password": "GET /y?password=SECRET HTTP/1.1",
    "after-tab": "a\thttps://u:SECRET@h/x",
    "after-newline": "a\nhttps://u:SECRET@h/x",
    "label-at-cut": "a" * 110 + "?token=SECRET",
    "user-info-at-cut": "x" * 105 + " https://user:SECRET@host/path",
    "bearer": "Authorization: Bearer SECRET",
}


@pytest.mark.parametrize("text", _MASKING_CORPUS.values(), ids=list(_MASKING_CORPUS))
def test_a_compared_value_masks_whatever_an_excerpt_masks(text: str) -> None:
    """White space is kept, not collapsed; every secret an excerpt hides
    stays hidden, shown whole or from any character on."""
    hidden = "SECRET" not in excerpt_text(text)
    for at in (None, 0, 3, len(text) - 8):
        shown = compared_text(ComparedValue(text, at))
        assert ("SECRET" not in shown) or not hidden, (at, shown)


#: An e with acute, built from its code point (a formatter writes an
#: escape back as the character).
_CAFE = "caf" + chr(0xE9)
#: (wheel, SBOM) values whose plain shown forms would look alike.
_LOOK_ALIKES = {
    "backslash-t-vs-tab": ("demo\\t", "demo\t"),
    "backslash-x00-vs-nul": ("demo\\x00", "demo\x00"),
    "nfc-vs-nfd": (
        unicodedata.normalize("NFC", _CAFE),
        unicodedata.normalize("NFD", _CAFE),
    ),
    "astral": ("x\U0001f600", "x\U0001f601"),
    "quote-styles": ("it's", "it\\'s"),
}


@pytest.mark.parametrize(
    ("wheel", "sbom"), _LOOK_ALIKES.values(), ids=list(_LOOK_ALIKES)
)
def test_look_alike_values_are_told_apart(
    caplog: pytest.LogCaptureFixture, wheel: str, sbom: str
) -> None:
    for text in _lines(caplog, wheel, sbom):
        found = _SIDES.search(text)
        assert found is not None, text
        shown_sbom, shown_wheel = found.groups()
        assert shown_sbom != shown_wheel
        # Told apart in ASCII: a reader's terminal may draw both alike.
        assert shown_sbom.encode("ascii", "replace") != shown_wheel.encode(
            "ascii", "replace"
        )


def test_a_non_ascii_difference_is_shown_as_an_ascii_literal() -> None:
    wheel, sbom = compared_pair("x\U0001f600", "x\U0001f601")
    assert compared_text(sbom).endswith("(from character 2: '\\U0001f601')")
    assert compared_text(wheel).endswith("(from character 2: '\\U0001f600')")


def test_distinct_ascii_values_get_no_note() -> None:
    assert compared_pair("demo", "demo2") == ("demo", "demo2")


_LOOP: list[object] = []
_LOOP.append(_LOOP)


@pytest.mark.parametrize(
    ("value", "shown"),
    [
        (["a  b\t"], "'[\"a  b\\\\t\"]'"),
        ({"b": 1, "a": None}, '\'{"a": null, "b": 1}\''),
        (5, "'5'"),
        # JSON refuses these: the shown form falls back to the value's repr.
        ({1}, "'{1}'"),
        (_LOOP, "'[[...]]'"),
    ],
    ids=["list", "dict", "int", "set", "circular"],
)
def test_a_value_not_text_is_shown_as_json(value: object, shown: str) -> None:
    assert compared_text(value) == shown


def test_a_subject_type_not_text_keeps_its_white_space(
    caplog: pytest.LogCaptureFixture,
) -> None:
    gap = s.CrossCheckGap(s.GAP_SUBJECT_NOT_PACKAGE, value=["a  b\t"])
    s.warn_cross_check_gaps(_LOG, "a.whl", [gap])
    (record,) = caplog.records
    assert "a  b\\\\t" in record.getMessage()
