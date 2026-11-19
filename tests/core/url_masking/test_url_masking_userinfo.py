# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the one user information rule
(:func:`pitloom.core.url_masking.userinfo_end`) as the masker, the refusal
of a stored value and the Git split read it, and for the account name of an
``ssh`` URL.

See also: test_url_masking_detect.py (the detector),
test_url_masking_differential.py (the deciders against each other) and
test_url_masking_given_path.py (the masker), all in this folder.
"""

from __future__ import annotations

import pytest

from pitloom.core.url_masking import (
    holds_url_credentials,
    is_account_name,
    masked_given_path,
    sanitize_url,
    sanitize_url_credentials,
    split_userinfo,
    userinfo_end,
)


@pytest.mark.parametrize(
    ("url", "plain"),
    [
        ("https://u:PW@h.example?mail=a@b.org", "https://h.example?mail=a@b.org"),
        ("https://TOKEN@h?contact=me@x.org", "https://h?contact=me@x.org"),
        ("https://:SECRET?x@h/ns", "https://h/ns"),
        ("https://u:p@ss@h/x", "https://h/x"),
        ("https://u:S3<CRET@h.example/x", "https://h.example/x"),
        ('https://u:S3"CRET@h/x', "https://h/x"),
        ("https://u:S3>CRET@h/x", "https://h/x"),
        ("https://u:S3 CRET@h/x", "https://h/x"),
        ("https://u:S3\tCRET@h/x", "https://h/x"),
        ('https://u:S3\\"CRET@h', "https://h"),
        ("https://u:S3'CRET@h/x", "https://h/x"),
    ],
    ids=[
        "host-before-query-at",
        "token-before-query-at",
        "empty-user-question",
        "last-at-wins",
        "angle",
        "double-quote",
        "closing-angle",
        "space",
        "tab",
        "escaped-quote",
        "single-quote",
    ],
)
def test_every_decider_reads_one_user_information(url: str, plain: str) -> None:
    """The refusal says so, the masker hides it and the Git split takes it
    out, each by the one rule."""
    split = split_userinfo(url)
    assert split is not None and split[0] == plain
    assert holds_url_credentials(url)
    assert "S3" not in masked_given_path(url) and "PW" not in masked_given_path(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://h?contact=me@x.org",
        "https://h:8080?x=a@b",
        "https://h#me@x.org",
        "https://[::1]:8080?x=a@b",
        "https://@h/x",
        "https://h/p@q",
    ],
    ids=["query", "port", "fragment", "ipv6", "empty", "path"],
)
def test_an_at_sign_after_a_host_is_no_user_information(url: str) -> None:
    assert split_userinfo(url) is None
    assert not holds_url_credentials(url)
    assert masked_given_path(url) == url


@pytest.mark.parametrize(
    ("url", "widest", "end"),
    [
        ("https://u:PW@h?m=a@b", False, 12),
        ("https://u:PW@h?m=a@b", True, 18),
        ('https://u:"@SECRET?x@h', False, 11),
        ('https://u:"@SECRET?x@h', True, 20),
        ("https://u:p@ss@h/x", False, 14),
        ("https://@h?x@y", False, None),
        ('https://@"x?y@h', False, 13),
    ],
    ids=["host", "host-widest", "quote", "quote-widest", "last", "empty", "bad"],
)
def test_the_masker_reads_the_widest_user_information(
    url: str, widest: bool, end: int | None
) -> None:
    """A masker runs to the last ``@`` (it hides a host, never a password);
    the refusal and git stop at an ``@`` followed by a host."""
    stop = url.find("/", 8)
    assert userinfo_end(url, 8, len(url) if stop < 0 else stop, widest=widest) == end


@pytest.mark.parametrize(
    ("url", "split"),
    [
        ("https://u:p?x@h/r", ("https://h/r", "u:p?x")),
        ("https://u:PW@h?m=a@b", ("https://h?m=a@b", "u:PW")),
        ("https://u%40x:p@h:8443/r", ("https://h:8443/r", "u%40x:p")),
        ("https://h/r", None),
        ("git@h:o/r", None),
    ],
    ids=["question", "host-first", "encoded", "none", "scp"],
)
def test_the_git_split_takes_the_same_user_information(
    url: str, split: tuple[str, str] | None
) -> None:
    assert split_userinfo(url) == split


@pytest.mark.parametrize(
    ("url", "kept"),
    [
        ("ssh://git@github.com/o/r", True),
        ("SSH://git@h/r", True),
        ("git+ssh://git@h/r.git@main", True),
        ("ssh://ssh.dev-az_1@h/r", True),
        ("ssh://git:PW@h/r", False),
        ("ssh://ghp_TOKEN@github.com/o/r", False),
        ("ssh://ghp_token@github.com/o/r", False),
        ("ssh://glpat-abc@h/r", False),
        ("ssh://a12345678@h/r", False),
        ("ssh://" + "a" * 33 + "@h/r", False),
        ("https://git@h/r", False),
    ],
    ids=[
        "git",
        "upper-scheme",
        "git-plus-ssh",
        "punctuation",
        "password",
        "token",
        "lower-token",
        "gitlab-token",
        "digits",
        "long",
        "https",
    ],
)
def test_an_ssh_account_name_is_accepted_and_a_token_refused(
    url: str, kept: bool
) -> None:
    """A user name alone on an ``ssh`` URL reaches the server; a password or
    a token-looking name is a credential. A namespace or a key refuses any
    user information unless *account* is set."""
    assert holds_url_credentials(url)
    assert holds_url_credentials(url, account=True) is not kept
    scheme, _, rest = url.partition("://")
    assert is_account_name(scheme, rest.partition("@")[0]) is kept


@pytest.mark.parametrize(
    ("text", "shown"),
    [
        ("alice:pw@host:o/r", "***:***@host:o/r"),
        ("t:alice:pw@host:o/r", "t:alice:pw@host:o/r"),
        ("see https://u:p@h/x and bob:pw@host:/srv/r", None),
        ("https://h?contact=me@x.org", "https://h?contact=me@x.org"),
    ],
    ids=["scp", "scp-after-colon", "both", "query"],
)
def test_sanitize_url_credentials_masks_scp_and_reads_the_rule(
    text: str, shown: str | None
) -> None:
    masked = sanitize_url_credentials(text)
    if shown is None:
        assert "pw" not in masked and ":p@" not in masked
    else:
        assert masked == shown


@pytest.mark.parametrize(
    ("url", "masked"),
    [
        ("https://u:p?x@h/r", "https://***:***@h/r"),
        ("https://h?contact=me@x.org", None),
        ("https:\\u:p@h\\r", "https://***:***@h\\r"),
        ("https://u:\\SECRET@h/r", "https://***:***@h/r"),
    ],
    ids=["question", "query", "windows", "opener-in-user-information"],
)
def test_a_text_that_is_one_url_reads_the_rule(url: str, masked: str | None) -> None:
    assert sanitize_url(url) == (masked or url)
