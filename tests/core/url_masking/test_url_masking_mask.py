# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The masker (:func:`pitloom.core.url_masking.masked_given_path`) hides all
the detector refuses, in a value or in free text, and leaves a PURL without
a hit as given.

See also: test_url_masking_given_path.py (its URL reading) and
test_url_masking_detect.py (the detector) in this folder.
"""

from __future__ import annotations

import pytest

from pitloom.core.url_masking import find_url_credentials, masked_given_path
from tests.core.url_masking._probe_corpus import encoded


@pytest.mark.parametrize(
    ("text", "shown"),
    [
        (
            "see pkg:generic/x?u=" + encoded("https://u:S3CRET@h/x", 2) + " ok",
            "see pkg:generic/x?u=*** ok",
        ),
        ("token ghp_T0KEN" + "aB3" * 10 + "x here", "token ghp_*** here"),
        ("clone alice:S3CRET@host:repo now", "clone ***:***@host:repo now"),
    ],
    ids=["encoded-qualifier", "token", "dotless-scp"],
)
def test_the_masker_hides_each_new_shape_in_free_text(text: str, shown: str) -> None:
    assert masked_given_path(text) == shown
    assert masked_given_path(shown) == shown


@pytest.mark.parametrize(
    "text",
    ["pkg:pypi/x@1.0", "see pkg:pypi/x@1.0#sub ok", "pkg:generic/x?checksum=sha256:ab"],
    ids=["no-qualifier", "subpath-in-prose", "clean-qualifier"],
)
def test_a_purl_without_a_hit_is_masked_as_given(text: str) -> None:
    assert masked_given_path(text) == text


_GHP = "ghp_T0KEN" + "aB3" * 10 + "x"


@pytest.mark.parametrize(
    ("text", "shown"),
    [
        (
            "pkg:g/x@1?download_url=https://u:S3CRET@h/x&note=" + encoded(_GHP, 1),
            "pkg:g/x@1?download_url=***&note=***",
        ),
        (
            "pkg:g/x@1?vcs_url=" + encoded("alice:S3CRET@github.com:o/r.git", 1),
            "pkg:g/x@1?vcs_url=***",
        ),
        ("pkg:g/x@1?token=S3CRET&a=1", "pkg:g/x@1?token=***&a=1"),
        ("pkg:g/x@1?note=Bearer%20ghp%5F" + _GHP[4:], "pkg:g/x@1?note=***"),
        ("pkg:g/x@1#sub/ghp%5F" + _GHP[4:], "pkg:g/x@1#***"),
    ],
    ids=[
        *("token-beside-a-refusal", "encoded-scp", "secret-key"),
        *("encoded-token-in-words", "encoded-token-in-subpath"),
    ],
)
def test_the_masker_hides_every_qualifier_the_detector_finds(
    text: str, shown: str
) -> None:
    """Each qualifier of a PURL that decodes to a finding is masked, not only
    the one that made the PURL refused."""
    assert masked_given_path(text) == shown


@pytest.mark.parametrize("brk", ["\t", "\n", "\r"], ids=["tab", "lf", "cr"])
def test_a_line_reads_a_password_through_a_tab_or_line_break(brk: str) -> None:
    """A URL parser deletes a tab or a line break, so the password holding
    one is still the password: a log line masks all of it."""
    text = f"URL=https://u:S3{brk}CRET@h/x bad"
    assert masked_given_path(text, line=True) == "URL=https://***:***@h/x bad"


def test_a_secret_value_runs_over_a_semicolon_in_every_reader() -> None:
    """``parse_qsl`` and the WHATWG parser read ``;`` as part of a value:
    the masker and the detector hide all of ``S3C;RET``; a path parameter
    opened by ``;`` still ends at the next ``;``."""
    url = "https://h/x?token=S3C;RET&a=1"
    assert masked_given_path(url) == "https://h/x?token=***&a=1"
    assert masked_given_path(f"see {url} ok", line=True) == (
        "see https://h/x?token=***&a=1 ok"
    )
    assert [f.shown for f in find_url_credentials(url)] == ["https://h/x?token=***&a=1"]
    path = "https://h/x;jsessionid=S3C;a=1?q=1"
    assert [f.shown for f in find_url_credentials(path)] == [
        "https://h/x;jsessionid=***;a=1?q=1"
    ]
    assert masked_given_path(path) == "https://h/x;jsessionid=***;a=1?q=1"


def test_a_purl_in_a_line_keeps_the_punctuation_after_it() -> None:
    text = "URL=pkg:g/x?token=S3CRET: not found"
    assert masked_given_path(text, line=True) == "URL=pkg:g/x?token=***: not found"
    for line in (False, True):
        enclosed = masked_given_path("<pkg:g/x?token=S3CRET>", line=line)
        assert enclosed == "<pkg:g/x?token=***>"


@pytest.mark.parametrize(
    "url",
    [
        "https://h/x?code=a;token=S3CRET",
        "https://h/x?token=ab:/c;S3CRET",
        "https://h/x?token=x;ab:/c;S3CRET",
    ],
    ids=["after-a-weak-value", "after-a-nested-url-start", "nested-url-mid-value"],
)
def test_only_a_secret_value_runs_over_a_semicolon(url: str) -> None:
    """A weak name's value (kept as written) ends at ``;``, so a secret
    after it is still found; a secret value that reaches a URL inside it
    runs over a ``;`` after that URL too, in the masker and the detector."""
    assert "S3CRET" not in masked_given_path(url)
    assert any(not f.weak for f in find_url_credentials(url))
