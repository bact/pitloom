# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The credential after a ``Bearer`` or ``Basic`` scheme
(:mod:`pitloom.core.url_masking._auth_schemes`), masked in a log line, and
the prose after such a word, kept.

See also: test_url_masking_boundary.py (where a scheme word may start) in
this folder.
"""

from __future__ import annotations

import pytest

from pitloom.core.url_masking import masked_given_path
from pitloom.log_masking import masked_text

_JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.sIg_-x9"


@pytest.mark.parametrize(
    ("text", "shown"),
    [
        (f"Authorization: Bearer {_JWT}", "Authorization: Bearer ***"),
        ("authorization: bearer 0123456789abcdef", "authorization: bearer ***"),
        ("Bearer abcdefghijklmnopqrst", "Bearer ***"),
        ("Bearer abcd~efgh", "Bearer ***"),
        ("Bearer abcd+efgh", "Bearer ***"),
        ("Bearer abcd/efgh", "Bearer ***"),
        ("Bearer abcdefgh=", "Bearer ***"),
        ("Bearer Abcd-Efgh-iJ", "Bearer ***"),
        ("Basic dXNlcjpwYXNzd29yZA==", "Basic ***"),
        ("Basic dXNlcjpwYXNz", "Basic ***"),
        ("BEARER\tabcd1234", "BEARER\t***"),
        ("Bearer%20abcd1234", "Bearer%20***"),
        ("x\\tBearer\\tabcd1234", "x\\tBearer\\t***"),
        ("x:Bearer  abcd1234", "x:Bearer  ***"),
        ("Bearer a.b.c.d.e.f.", "Bearer ***."),
        ("Bearer abc.def.Bearer 12345678x", "Bearer *** ***"),
        ("Bearer bearer 1234abcd", "Bearer bearer ***"),
        ("Bearer ghp_" + "aB3" * 12, "Bearer ghp_***"),
        (f"-H 'Authorization: Bearer {_JWT}'", "-H 'Authorization: Bearer ***'"),
    ],
    ids=[
        "jwt",
        "lower",
        "twenty-letters",
        "tilde",
        "plus",
        "slash",
        "padding",
        "mixed-case",
        "basic",
        "basic-unpadded",
        "tab",
        "pct20",
        "escaped-tab",
        "two-spaces",
        "dot-kept",
        "two-schemes",
        "scheme-twice",
        "known-token",
        "curl",
    ],
)
def test_the_credential_after_a_scheme_is_masked(text: str, shown: str) -> None:
    """The run after a scheme and its separators is written ``***``, the
    scheme kept; masking it again changes nothing."""
    assert masked_text(text) == shown
    assert masked_text(shown) == shown
    assert masked_given_path(text) == shown


@pytest.mark.parametrize(
    "text",
    [
        "the bearer of bad news",
        "Bearer token required",
        "Use Bearer authentication.",
        "Basic Authentication",
        "a basic well-formed document",
        "basic 2024-edition",
        "basic 20240101-x",
        "Basic abcdef1",
        'WWW-Authenticate: Bearer realm="api", error="invalid_token"',
        "Authorization: Bearer <token>",
        "Bearer $GITHUB_TOKEN",
        "Bearer access_token",
        "the bearer co-signer",
        "Bearer Token-Based scheme",
        "Bearer abcdef1",
        "Bearer ABCDEFGHIJKLMNOPQRS",
        "Bearer abcdefghijklmnopqrs",
        "basicConfiguration",
        "x-basic abc12345678",
        "x_bearer abc12345678",
        "x1bearer abc12345678",
        "subearer abc12345678",
        "Bearer: abc12345678",
    ],
    ids=[
        "bad-news",
        "required",
        "sentence",
        "title-case",
        "hyphenated",
        "year-hyphen",
        "date-hyphen",
        "basic-seven",
        "challenge",
        "placeholder",
        "variable",
        "snake-case",
        "hyphen-only",
        "title-words",
        "seven",
        "upper-nineteen",
        "lower-nineteen",
        "glued",
        "after-hyphen",
        "after-underscore",
        "after-digit",
        "inside-word",
        "colon",
    ],
)
def test_prose_after_a_scheme_word_is_kept(text: str) -> None:
    """Prose after a scheme word, a run too short or of plain letters, a
    ``Basic`` run that is no base64, and a scheme word glued to another, are
    printed as written."""
    assert masked_text(text) == text
