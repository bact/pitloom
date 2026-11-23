# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The credential after an ``Authorization`` header's scheme or a ``Bearer``
or ``Basic`` scheme word (:mod:`pitloom.core.url_masking._auth_schemes`),
masked in a log line, and the prose after such a word, kept.

See also: test_url_masking_boundary.py (where a scheme word may start) in
this folder.
"""

from __future__ import annotations

import pytest

from pitloom.core.url_masking import _auth_schemes, masked_given_path
from pitloom.log_masking import masked_text
from pitloom.logging_config import loggable
from pitloom.messages import escaped_name

_JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.sIg_-x9"


@pytest.mark.parametrize(
    ("text", "shown"),
    [
        pytest.param(f"Bearer {_JWT}", "Bearer ***", id="jwt"),
        pytest.param("Bearer abcdefghijklmnopqrst", "Bearer ***", id="twenty-letters"),
        pytest.param("Bearer abcd~efgh", "Bearer ***", id="tilde"),
        pytest.param("Bearer abcd+efgh", "Bearer ***", id="plus"),
        pytest.param("Bearer dXNl/cjpwYXNz", "Bearer ***", id="slash-random-word"),
        pytest.param("Bearer abcdefgh=", "Bearer ***", id="padding"),
        pytest.param("Bearer Abcd-Efgh-iJ", "Bearer ***", id="mixed-case"),
        pytest.param("Bearer s3cr3tvalue99", "Bearer ***", id="one-lower"),
        pytest.param("Bearer 12345678", "Bearer ***", id="digits-only"),
        pytest.param("Bearer abcd12efgh", "Bearer ***", id="digits-inside"),
        pytest.param("Bearer 1234abcd", "Bearer ***", id="digits-first"),
        pytest.param("Basic dXNlcjpwYXNzd29yZA==", "Basic ***", id="basic"),
        pytest.param("Basic dXNlcjpwYXNz", "Basic ***", id="basic-unpadded"),
        pytest.param("Basic dXNlcjpwYXNzd28=", "Basic ***", id="basic-one-pad"),
        pytest.param("Bearer x86_64-linux", "Bearer ***", id="over-masked-arch"),
        pytest.param("Bearer iPhone15Pro", "Bearer ***", id="over-masked-name"),
        pytest.param("BEARER\tabcd1234", "BEARER\t***", id="tab"),
        pytest.param("Bearer\xa0abcd1234", "Bearer\xa0***", id="nbsp"),
        pytest.param("Bearer%20abcd1234", "Bearer%20***", id="pct20"),
        pytest.param("x:Bearer  abcd1234", "x:Bearer  ***", id="two-spaces"),
        pytest.param("Bearer eyJh.eyJz.", "Bearer ***.", id="dot-kept"),
        pytest.param(
            "Bearer eyJh.eyJz.Bearer 12345678x", "Bearer *** ***", id="two-schemes"
        ),
        pytest.param("Bearer bearer 1234abcd", "Bearer bearer ***", id="scheme-twice"),
        pytest.param("Bearer ghp_" + "aB3" * 12, "Bearer ghp_***", id="known-token"),
        pytest.param("a\tBearer s3cr3tvalue99.gguf", "a\tBearer ***", id="extension"),
    ],
)
def test_the_credential_after_a_scheme_word_is_masked(text: str, shown: str) -> None:
    """A run after a scheme word that looks random is written ``***``, the
    scheme kept; masking it again changes nothing."""
    assert masked_text(text) == shown
    assert masked_text(shown) == shown
    assert masked_given_path(text) == shown


@pytest.mark.parametrize(
    "raw",
    [
        "Authorization: Bearer\ts3cr3tvalue99",
        "Bearer\ts3cr3tvalue99",
        "Basic\tdXNlcjpwYXNz",
        "Bearer\xa0s3cr3tvalue99",
        "Authorization: Basic\xa0abcdefghij",
    ],
    ids=["header", "bearer", "basic", "nbsp", "header-nbsp"],
)
def test_an_escaped_separator_once_or_doubled_is_a_separator(raw: str) -> None:
    """A tab or a no-break space after the scheme, escaped once or twice,
    still separates the credential, which is masked."""
    # loggable() leaves printable text as it is: ascii() escapes it again.
    for escaped in (loggable(raw), ascii(loggable(raw))):
        assert raw not in escaped
        shown = masked_text(escaped)
        secret = raw.split()[-1].rpartition("\xa0")[2].rpartition("\t")[2]
        assert secret not in shown and "***" in shown, escaped


@pytest.mark.parametrize(
    ("text", "shown"),
    [
        pytest.param(
            f"Authorization: Bearer {_JWT}", "Authorization: Bearer ***", id="jwt"
        ),
        pytest.param(
            "authorization: bearer abcdefghij", "authorization: bearer ***", id="lower"
        ),
        pytest.param(
            "Authorization: Bearer ABCDEFGHIJKLMNOPQRS",
            "Authorization: Bearer ***",
            id="upper",
        ),
        pytest.param(
            "Authorization: Bearer Abcdefghijklmnop",
            "Authorization: Bearer ***",
            id="title",
        ),
        pytest.param(
            "Authorization: Bearer abcdefgh-ijklmno",
            "Authorization: Bearer ***",
            id="hyphen",
        ),
        pytest.param(
            "Authorization: Bearer abc.", "Authorization: Bearer ***.", id="dot-kept"
        ),
        pytest.param(
            "Authorization: token abcdefgh12345678",
            "Authorization: token ***",
            id="token",
        ),
        pytest.param(
            "Authorization : Bearer abcdefghij", "Authorization : Bearer ***", id="gap"
        ),
        pytest.param(
            "Authorization:\\tBearer abcdefghij",
            "Authorization:\\tBearer ***",
            id="escaped-gap",
        ),
        pytest.param(
            '"Authorization": "Bearer abcdefghij"',
            '"Authorization": "Bearer ***"',
            id="json",
        ),
        pytest.param(
            '{\\"Authorization\\": \\"Bearer abcdefghij\\"}',
            '{\\"Authorization\\": \\"Bearer ***\\"}',
            id="escaped-json",
        ),
        pytest.param(
            "Proxy-Authorization=Basic abcdefgh",
            "Proxy-Authorization=Basic ***",
            id="proxy",
        ),
        pytest.param(
            "Authorization: Bearer token required",
            "Authorization: Bearer *** required",
            id="prose-word",
        ),
        pytest.param(
            'Authorization: Digest username="u", response="6629fae4", qop=auth',
            'Authorization: Digest username="u", response="***", qop=auth',
            id="digest",
        ),
        pytest.param(
            'Authorization: Digest a=1, Authorization: Digest response="r1"',
            'Authorization: Digest a=1, Authorization: Digest response="***"',
            id="digest-twice",
        ),
        pytest.param(
            'Authorization: Digest a=1\nresponse="r1"',
            'Authorization: Digest a=1\nresponse="r1"',
            id="digest-next-line",
        ),
        pytest.param(
            "Authorization: Basic Bearer abcd1234efgh",
            "Authorization: Basic *** ***",
            id="scheme-word-as-credential",
        ),
        pytest.param(
            "Authorization: token Bearer s3cr3tvalue99",
            "Authorization: token *** ***",
            id="token-then-bearer",
        ),
    ],
)
def test_the_credential_after_a_header_name_is_masked_whatever_its_shape(
    text: str, shown: str
) -> None:
    """After ``Authorization`` or ``Proxy-Authorization``, ``:`` or ``=``,
    the credential is masked whole whatever its length or shape; a
    ``Digest`` header's ``response=`` value on that line only."""
    assert masked_text(text) == shown
    assert masked_text(shown) == shown


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
        "Bearer error=invalid_token",
        "Authorization: Bearer <token>",
        "Authorization: Bearer ${TOKEN}",
        "Authorization: Bearer $GITHUB_TOKEN",
        "X-Authorization: Bearer abcdefghij",
        "Bearer $GITHUB_TOKEN",
        "Bearer access_token",
        "the bearer co-signer",
        "Bearer Token-Based scheme",
        "Bearer abcdef1",
        "Bearer s3cr3tx",
        "Basic s3cr3t-value",
        "Basic dXNlcjpwYXNz===",
        "Basic DevOps2024",
        "Bearer ABCDEFGHIJKLMNOPQRS",
        "Bearer abcdefghijklmnopqrs",
        "Bearer a.b.c.d.e.f",
        "Bearer tokens/authorization-headers",
        "basic types/values",
        "Basic usage/configuration",
        "use bearer tokens/keys",
        "requires basic understanding/skill",
        "Basic tutorial2024",
        "see Bearer RFC-6750-style",
        "Basic Latin1Supplement",
        "bearer requests.auth.HTTPBearer",
        "https://h/guide/bearer%20tokens/setup",
        "basicConfiguration",
        "x-basic abc12345678",
        "x_bearer abc12345678",
        "x1bearer abc12345678",
        "subearer abc12345678",
        "Bearer: abc12345678",
    ],
)
def test_prose_after_a_scheme_word_is_kept(text: str) -> None:
    """Prose after a scheme word (a run too short, of words, names or
    versions), a ``Basic`` run that is no base64, a placeholder after a
    header name, and a scheme word or header name glued to another, are
    printed as written."""
    assert masked_text(text) == text


@pytest.mark.parametrize(
    ("name", "shown"),
    [
        ("Bearer Token.txt", "Bearer Token.txt"),
        ("a\tBearer s3cr3tvalue99.gguf", "'a\\tBearer ***'"),
    ],
    ids=["prose-name", "credential-name"],
)
def test_a_file_name_after_a_scheme_word(name: str, shown: str) -> None:
    """A file name holding a scheme word and a prose word prints whole; one
    holding a credential prints it masked with the extension after it."""
    assert escaped_name(name) == shown


def test_a_digest_header_is_read_up_to_the_next_header_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ``response=`` of each of many ``Digest`` headers on one line is
    looked for up to the next header: the characters searched add up to
    the text's length, not its square (a line of many headers would
    otherwise be read once per header)."""
    searched: list[int] = []
    # pylint: disable-next=protected-access
    real = _auth_schemes._DIGEST_RESPONSE

    # pylint: disable-next=too-few-public-methods
    class _Spy:
        def search(self, text: str, pos: int, endpos: int) -> object:
            searched.append(endpos - pos)
            return real.search(text, pos, endpos)

    monkeypatch.setattr(_auth_schemes, "_DIGEST_RESPONSE", _Spy())
    text = "Authorization: Digest a=1, " * 200 + 'response="r1"'
    assert _auth_schemes.mask_auth_schemes(text).endswith('response="***"')
    assert len(searched) == 200 and sum(searched) <= len(text)
