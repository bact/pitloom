# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The value of a header that carries a secret and of each cookie
(:mod:`pitloom.core.url_masking._headers`), masked in a log line, the header
and cookie names kept; other headers and placeholders kept.

See also: test_url_masking_auth_schemes.py (the ``Authorization`` header) in
this folder.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import pytest

from pitloom.core.url_masking import _headers, masked_given_path
from pitloom.log_masking import mask_record, mask_third_party_record, masked_text

# Fake secrets, built at run time so no secret-shaped literal sits in source.
_KEY = "k3y" + "Val" + "ue9"
_SID = "s1d" + "Val" + "ue8"
_OTHER = "0th" + "erV" + "al7"
#: A fake secret no other pass masks (no upper case, no token shape).
_PLAIN = "abcdefgh" + "12"
#: The closed list, written out: a name added to the module without a test
#: fails :func:`test_the_list_is_the_tested_one`, a name dropped fails its row.
_LISTED = (
    "Access-Token",
    "Api-Key",
    "Job-Token",
    "Ocp-Apim-Subscription-Key",
    "Private-Token",
    "X-Access-Token",
    "X-Amz-Security-Token",
    "X-Api-Key",
    "X-Auth-Token",
    "X-Goog-Api-Key",
    "X-JFrog-Art-Api",
    "X-Registry-Auth",
    "X-Vault-Token",
)


def _masked_line(text: str) -> str:
    """The masker of a log line, as :func:`masked_text` calls it."""
    return masked_given_path(text, line=True, free_params=True)


#: Each masker that runs this pass: the pass alone, a log line, the sink's.
_MASKERS: list[Callable[[str], str]] = [
    _headers.mask_secret_headers,
    _masked_line,
    masked_text,
]
_MASKER_IDS = ["pass", "line", "masked_text"]


def _assert_masked(masker: Callable[[str], str], text: str, shown: str) -> None:
    """*text* masked is *shown*, and no fake secret is in it."""
    masked = masker(text)
    assert masked == shown
    for secret in (_KEY, _SID, _OTHER, _PLAIN):
        assert secret not in masked


def test_the_list_is_the_tested_one() -> None:
    assert _headers.SECRET_HEADERS == _LISTED


@pytest.mark.parametrize("masker", _MASKERS, ids=_MASKER_IDS)
@pytest.mark.parametrize("name", _LISTED)
@pytest.mark.parametrize("case", [str, str.lower, str.upper], ids=["as", "lo", "up"])
def test_each_listed_header_hides_its_value(
    masker: Callable[[str], str], name: str, case: Callable[[str], str]
) -> None:
    """Every name of the closed list, in any case, hides its value; the
    list is sorted (one place to add a name)."""
    assert list(_headers.SECRET_HEADERS) == sorted(_headers.SECRET_HEADERS)
    header = case(name)
    _assert_masked(masker, f"{header}: {_KEY}", f"{header}: ***")


@pytest.mark.parametrize("masker", _MASKERS, ids=_MASKER_IDS)
@pytest.mark.parametrize(
    ("text", "shown"),
    [
        pytest.param("X-Api-Key:" + _KEY, "X-Api-Key:***", id="no-space"),
        pytest.param(f"X-Api-Key:\t{_KEY}", "X-Api-Key:\t***", id="tab"),
        pytest.param(f"X-Api-Key:\\t{_KEY}", "X-Api-Key:\\t***", id="escaped-tab"),
        pytest.param(f"\\tX-Api-Key: {_KEY}", "\\tX-Api-Key: ***", id="after-escape"),
        pytest.param(f'{{"X-Api-Key": "{_KEY}"}}', '{"X-Api-Key": "***"}', id="json"),
        pytest.param(
            f'{{\\"X-Api-Key\\": \\"{_KEY}\\"}}',
            '{\\"X-Api-Key\\": \\"***\\"}',
            id="escaped-json",
        ),
        pytest.param(
            f"{{'x-api-key': '{_KEY}'}}", "{'x-api-key': '***'}", id="dict-repr"
        ),
        pytest.param(
            f"X-Api-Key: {_KEY} Private-Token: {_OTHER}",
            "X-Api-Key: *** Private-Token: ***",
            id="two-headers",
        ),
        pytest.param(
            f"X-Api-Key: X-Auth-Token: {_KEY}",
            "X-Api-Key: X-Auth-Token: ***",
            id="next-header-bounds",
        ),
        pytest.param(
            f"X-Auth-Token: Bearer {_KEY}", "X-Auth-Token: Bearer ***", id="scheme"
        ),
        pytest.param(
            f"X-Auth-Token: token {_PLAIN}", "X-Auth-Token: token ***", id="token"
        ),
        pytest.param(
            f"X-Api-Key: Bearer\\t{_PLAIN}",
            "X-Api-Key: Bearer\\t***",
            id="scheme-escaped-tab",
        ),
        pytest.param(f"X-Api-Key: }}{_PLAIN}", "X-Api-Key: ***", id="close-brace"),
        pytest.param(f"X-Api-Key: >{_PLAIN}", "X-Api-Key: ***", id="close-angle"),
        pytest.param(
            f"Cookie: session={_SID}; other={_OTHER}",
            "Cookie: session=***; other=***",
            id="cookie",
        ),
        pytest.param(
            f"Set-Cookie: sid={_SID}; Path=/; Domain=x.org; SameSite=Lax; HttpOnly",
            "Set-Cookie: sid=***; Path=/; Domain=x.org; SameSite=Lax; HttpOnly",
            id="set-cookie-attributes",
        ),
        pytest.param(
            f"set-cookie: sid={_SID}; max-age=60; path=/; secure",
            "set-cookie: sid=***; max-age=60; path=/; secure",
            id="set-cookie-lower",
        ),
        pytest.param(
            "Set-Cookie: sid=abc; Expires=Wed, 21 Oct 2015 07:28:00 GMT",
            "Set-Cookie: sid=***; Expires=Wed, 21 Oct 2015 07:28:00 GMT",
            id="set-cookie-expires",
        ),
        pytest.param(
            "Set-Cookie: sid=abc; Priority=High",
            "Set-Cookie: sid=***; Priority=High",
            id="set-cookie-priority",
        ),
        pytest.param("Cookie: sid=}x", "Cookie: sid=***", id="cookie-close-brace"),
        pytest.param("Cookie: a=; b=c", "Cookie: a=; b=***", id="cookie-empty"),
        # An escaped line end ends the header: x=yz is no cookie of it.
        pytest.param("Cookie: a=b\\nx=yz", "Cookie: a=***\\nx=yz", id="escaped-lf"),
        pytest.param(
            'Cookie: sid=\\\\"abcd efgh\\\\"',
            'Cookie: sid=\\\\"***\\\\"',
            id="quoted-escaped-twice",
        ),
        # A Cookie header has no attributes: a cookie named Path is a cookie.
        pytest.param(f"Cookie: Path={_SID}", "Cookie: Path=***", id="cookie-path"),
        pytest.param(
            f'{{"Cookie": "a={_SID}; b=\\"{_OTHER}\\"", "Accept": "x=y"}}',
            '{"Cookie": "a=***; b=\\"***\\"", "Accept": "x=y"}',
            id="cookie-json",
        ),
        pytest.param(
            f'{{\\"Cookie\\": \\"a={_SID}\\", \\"Accept\\": \\"x=y\\"}}',
            '{\\"Cookie\\": \\"a=***\\", \\"Accept\\": \\"x=y\\"}',
            id="cookie-escaped-json",
        ),
        pytest.param(
            f"Cookie: a={_SID}\nAccept: x=y", "Cookie: a=***\nAccept: x=y", id="lf"
        ),
        pytest.param(
            f'Cookie: sid="{_SID} {_OTHER}"; a=b',
            'Cookie: sid="***"; a=***',
            id="spaced",
        ),
        pytest.param(f'[("X-Api-Key", "{_KEY}")]', '[("X-Api-Key", "***")]', id="pair"),
        pytest.param(
            f"[('cookie', 'sid={_SID}'), ('accept', 'x=y')]",
            "[('cookie', 'sid=***'), ('accept', 'x=y')]",
            id="cookie-pair",
        ),
        # Prose after a header name is masked as after Authorization:.
        pytest.param(
            "the X-Api-Key: header must be set",
            "the X-Api-Key: *** must be set",
            id="prose",
        ),
    ],
)
def test_header_forms(masker: Callable[[str], str], text: str, shown: str) -> None:
    """A header in a line, JSON, escaped JSON or a dict repr, several on a
    line, and cookies: each value masked, the names kept."""
    _assert_masked(masker, text, shown)


@pytest.mark.parametrize("masker", _MASKERS, ids=_MASKER_IDS)
@pytest.mark.parametrize(
    "text",
    [
        pytest.param(f"{name}: {_KEY}", id=name)
        for name in (
            "Session-Id",
            "Key-Value",
            "Cache-Key",
            "Sort-Key",
            "Primary-Key",
            "Public-Key",
            "X-Request-Id",
            "Content-Type",
            "X-Api-Key-Id",
            "My-X-Api-Key",
            "X_Api-Key",
        )
    ]
    + [
        pytest.param("X-Api-Key: <your key>", id="angle"),
        pytest.param("X-Api-Key: ${API_KEY}", id="braces"),
        pytest.param("Private-Token: $GITLAB_TOKEN", id="dollar"),
        pytest.param(f"X-Api-Key: {{{_PLAIN}}}", id="brace"),
        pytest.param(f"X-Api-Key: *{_PLAIN}", id="star"),
        pytest.param(f"X-Api-Key: ${_PLAIN}", id="dollar-word"),
        pytest.param(f"X-Api-Key: <{_PLAIN}>", id="angle-word"),
        pytest.param("X-Api-Key: ***", id="masked"),
        pytest.param("Cookie: (none)", id="cookie-no-pair"),
        pytest.param("Cookie: sid=<value>", id="cookie-placeholder"),
        pytest.param("Cookie: sid={abc}", id="cookie-brace"),
        pytest.param("Cookie: sid=$X", id="cookie-dollar"),
        pytest.param("Cookie: sid=*x", id="cookie-star"),
        pytest.param("Set-Cookie: Path=/; Secure", id="attributes-only"),
        pytest.param("X-Api-Key header is required", id="no-colon"),
        pytest.param(f"X-Api-Key:\n{_KEY}", id="line-break"),
        pytest.param(f'"X-Api-Key", {_KEY}', id="pair-unquoted-value"),
        pytest.param(f'X-Api-Key, "{_KEY}"', id="pair-unquoted-name"),
    ],
)
def test_kept(masker: Callable[[str], str], text: str) -> None:
    """Another header, a longer name or one glued to a word before it, a
    placeholder and a value on the next line are kept."""
    assert masker(text) == text


@pytest.mark.parametrize(
    ("text", "shown"),
    [
        pytest.param(
            f"Authorization: Bearer {_KEY} X-Api-Key: {_OTHER}",
            "Authorization: Bearer *** X-Api-Key: ***",
            id="after-authorization",
        ),
        pytest.param(
            f"X-Api-Key: Bearer {_KEY}", "X-Api-Key: Bearer ***", id="scheme-in-value"
        ),
        pytest.param("X-Api-Key: ghp_" + "a1" * 18, "X-Api-Key: ***", id="token-shape"),
    ],
)
def test_with_the_other_passes(text: str, shown: str) -> None:
    """This pass reads the text the ``Authorization`` and token passes have
    masked: no piece of either credential is shown."""
    masked = masked_text(text)
    assert masked == shown
    assert _KEY not in masked and _OTHER not in masked and "a1a1" not in masked


@pytest.mark.parametrize(
    ("name", "mask"),
    [
        pytest.param("pitloom.test_headers", mask_record, id="pitloom"),
        pytest.param("urllib3.connectionpool", mask_third_party_record, id="urllib3"),
    ],
)
def test_a_log_record_is_masked(
    name: str, mask: Callable[[logging.LogRecord], None]
) -> None:
    """A record's header and cookie values are masked by the sink."""
    record = logging.LogRecord(
        name, logging.DEBUG, __file__, 1, "send: %s", (f"Cookie: sid={_SID}",), None
    )
    mask(record)
    message = record.getMessage()
    assert message == "send: Cookie: sid=***"
    assert _SID not in message
