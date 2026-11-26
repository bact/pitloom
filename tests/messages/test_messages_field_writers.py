# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The writers a caller passes a free field's value through
(:func:`pitloom.messages.escaped_name`, :func:`pitloom.messages.url_text`):
masked first, then cut, then escaped, so an escape never hides a credential
from the masker and a cut never shows a credential's start.

See also: tests/messages/test_messages_fields.py (the other writers) and
tests/core/url_masking/test_url_masking_boundary.py (the masker's reading of
an escaped text).
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from pitloom.assemble import generate_model_sbom
from pitloom.extract.remote import RemoteSourceError, fetch_git_project
from pitloom.extract.remote._git_credentials import split_credentials
from pitloom.extract.remote._http_errors import shown_url
from pitloom.extract.remote.pypi_url import parse_pypi_url
from pitloom.messages import escaped_name, url_text
from pitloom.messages._field_writers import (
    NAME_CHARACTERS,
    NAME_CUT_MARK,
    entity_text,
    failure_text,
    file_text,
    free_text,
)

_BODY = "T0KEN" + "aB3" * 10 + "x"
_TOKEN = f"ghp_{_BODY}"


@pytest.mark.parametrize("write", [escaped_name, url_text, shown_url])
@pytest.mark.parametrize("control", ["\t", "\x1b", "\x7f"], ids=["tab", "esc", "del"])
def test_a_token_after_a_control_character_is_masked_then_escaped(
    write: object, control: str
) -> None:
    """A name or URL holding a control character and a token right after it
    prints the token masked and the control character escaped."""
    assert callable(write)
    shown = write(f"https://h.example/o/r/{control}{_TOKEN}?q=1")
    assert _BODY not in shown and "ghp_***" in shown
    assert control not in shown and ascii(control)[1:-1] in shown


@pytest.mark.parametrize("write", [escaped_name, url_text, shown_url])
def test_a_token_split_by_a_format_character_is_masked_before_the_escape(
    write: object,
) -> None:
    """A zero-width space inside a token: the masker reads the raw text
    without it and masks the token; escaped first, the token would be two
    runs of letters joined by ``\\u200b``, which no shape matches."""
    assert callable(write)
    half = _BODY[:18]
    shown = write(f"https://h.example/o/ghp_{half}\u200b{_BODY[18:]}")
    assert half not in shown and "ghp_***" in shown


@pytest.mark.parametrize("write", [url_text, shown_url])
def test_a_url_s_credentials_are_masked_whole(write: object) -> None:
    """The user information of a URL is masked whole (one URL's reading:
    a password holding a space), and a ``Bearer`` credential after it."""
    assert callable(write)
    shown = write("https://u:pa ss@h.example/o?x=Bearer abcd1234efgh")
    assert "pa ss" not in shown and "abcd1234" not in shown
    assert shown.startswith("https://***:***@h.example/o")


def test_a_name_is_masked_before_it_is_cut_and_escaped_after() -> None:
    """A token across the cut is masked whole (a cut first would show its
    start), and the escaped literal keeps its closing quote (an escape
    before the cut would lose it)."""
    head = "a" * (NAME_CHARACTERS - 8)
    shown = escaped_name(f"{head}\t{_TOKEN} {'b' * 50}")
    assert "T0KEN" not in shown and "ghp_***" in shown
    assert shown.startswith("'") and shown.endswith(f"{NAME_CUT_MARK}'")
    assert escaped_name("plain") == "plain"


def _fetch(url: str) -> None:
    with fetch_git_project(url):
        pass


_SPLIT = "ghp_" + _BODY[:18] + "\u200b" + _BODY[18:]


@pytest.mark.parametrize(
    ("refuse", "url"),
    [
        (parse_pypi_url, f"https://pypi.org/project/x!/{_SPLIT}"),
        (generate_model_sbom, f"https://pypi.org/project/x/{_SPLIT}"),
        (_fetch, f"https://pypi.org/project/x/{_SPLIT}"),
        (lambda url: split_credentials([url]), f"https://u:p@ex%41mple.com/{_SPLIT}"),
    ],
    ids=["pypi-url", "model-sbom", "git-fetch", "git-host"],
)
def test_each_caller_writes_a_refused_url_masked_then_escaped(
    refuse: Callable[[str], object], url: str
) -> None:
    """Each refusal naming the URL it was given writes it through
    :func:`url_text`: a token split by a zero-width space is masked; escaped
    first, it would be printed."""
    with pytest.raises((ValueError, RemoteSourceError)) as excinfo:
        refuse(url)
    message = str(excinfo.value)
    assert _BODY[:18] not in message and "ghp_***" in message


_LABELS = ["Request ID", "Amzn Trace ID", "Amz CF ID"]


@pytest.mark.parametrize("label", _LABELS, ids=["request", "amzn", "amz-cf"])
def test_a_dropped_request_id_does_not_glue_a_token(label: str) -> None:
    """The token is masked before the request id is dropped: masked after
    it only, ``abcghp_...`` reads as one word, which no shape matches. The
    mirror, user information the drop joins, is masked after it."""
    glued = failure_text(RuntimeError(f"abc({label}: a){_TOKEN}"))
    assert _BODY not in glued and glued == "abcghp_***"
    joined = failure_text(RuntimeError(f"https://u:pw99x({label}: a)@h"))
    assert "pw99x" not in joined and joined == "https://***:***@h"


_ZERO_WIDTH_SPLIT = _TOKEN[:10] + "\u200b" + _TOKEN[10:]


@pytest.mark.parametrize(
    "write", [free_text, file_text, entity_text], ids=["free", "file", "entity"]
)
@pytest.mark.parametrize(
    ("value", "secrets", "masked_form"),
    [
        (f"see {_ZERO_WIDTH_SPLIT}\t", (_BODY[:6], _BODY[6:]), "ghp_***"),
        ("alice:p\u00e4ssw0rd9@host:o/r\t", ("alice", "ssw0rd9"), "***:***@host"),
    ],
    ids=["zero-width", "scp-non-ascii"],
)
def test_a_writer_masks_before_it_escapes(
    write: Callable[[object], str],
    value: str,
    secrets: tuple[str, ...],
    masked_form: str,
) -> None:
    """Escaped first, ``\\u200b`` stands inside the token and ``\\xe4``
    inside the password, which no shape matches."""
    shown = write(value)
    assert not any(secret in shown for secret in secrets)
    assert masked_form in shown and shown.endswith("\\t'")
