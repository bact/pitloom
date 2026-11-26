# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The credential detector (:func:`pitloom.core.url_masking.find_url_credentials`):
a URL-typed value read as a whole, never prose; no weaker on such values
than the SBOM strip it replaced (the corpus records what that changed);
never showing what it finds; the masker hiding all it refuses; weak names
told and not refused.

See also: _probe_corpus.py (the corpus), test_url_masking_hits.py (each
kind of value and 1 MiB timings), test_url_masking_tokens.py (token shapes),
test_url_masking_mask.py (the masker) and test_url_masking_credentials.py
(the refusal surfaces) in this folder.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable

import pytest

from pitloom.core.url_masking import (
    Finding,
    find_url_credentials,
    holds_url_credentials,
    masked_given_path,
)
from pitloom.core.url_masking._hits import normalised
from tests.core.url_masking._probe_corpus import PLANTED, PROBES


@pytest.mark.parametrize(
    ("probe", "text", "changed", "refused"), PROBES, ids=[r[0] for r in PROBES]
)
def test_the_detector_refuses_what_the_strip_changed_and_masks_it(
    probe: str, text: str, changed: bool, refused: bool
) -> None:
    """Every corpus value the strip changed is refused, and no sentence is;
    a reviewed false positive is not refused; no finding shows a planted
    secret, and the masker's text of a refused value shows none either."""
    found = find_url_credentials(text, account=True)
    assert any(not f.weak for f in found) is refused
    if probe.startswith("prose-"):
        assert not found
    elif changed:
        assert refused
    for finding in found:
        assert not any(secret in finding.shown for secret in PLANTED)
        assert finding.shown in (
            masked_given_path(finding.view),
            # A view a decode or the strip made: the whole text masked.
            masked_given_path(text),
            finding.view.partition("=")[0] + "=***",
        )
    if refused:
        assert not any(secret in masked_given_path(text) for secret in PLANTED)


def test_refusal_reads_a_whole_value_and_never_prose() -> None:
    """Neither the detector nor the refusal has a free-text reading: a
    sentence holding a credentialed URL is no finding, though a log line's
    masker still hides its credential."""
    for function in (find_url_credentials, holds_url_credentials):
        assert "whole" not in inspect.signature(function).parameters
    sentence = "see https://u:S3CRET@h.example/x for details"
    assert not find_url_credentials(sentence)
    assert holds_url_credentials(sentence.split()[1])
    assert "S3CRET" not in masked_given_path(sentence, line=True)


@pytest.mark.parametrize(
    ("text", "kinds"),
    [
        ("https://h.example/x?code=abc", {"weak"}),
        ("https://h.example/x?code=1?session=2", {"weak"}),
        ("https://h.example/x?code=1?token=T0KEN", {"weak", "secret"}),
        ("https://h/a b?token=T0KEN", {"secret"}),
        ("https://x y:S3CRET@h/x", {"secret"}),
        ("x[a] @ https://o'brien:S3CRET@h.example/x.whl", {"secret"}),
        ("x @ git+ssh://git@h.example/r", {"account"}),
        ("x @ alice:S3CRET@host.example:o/r", set()),
        ("a://u:S3CRET@h/x", {"secret"}),
        ("C:\\u@h\\x", set()),
        ("build:42@ci:linux", {"scp"}),
        ("foo:bar@baz@qux:path", {"scp"}),
        ("build:42@ci:linux now", set()),
        ("", set()),
    ],
    ids=[
        *("weak", "weak-in-weak", "secret-in-weak", "space-path", "space-user"),
        *("requirement", "requirement-account", "requirement-scp"),
        *("one-letter-scheme", "drive", "scp", "scp-at"),
        *("scp-sentence", "empty"),
    ],
)
def test_each_value_finds_its_kind(text: str, kinds: set[str]) -> None:
    """A weak name is told, not refused; a URL value is read as ``urllib``
    reads it, white space and quotes included; a requirement's URL is read
    so (an scp-style address is no direct reference); an scp-style address
    is one only as the whole value."""
    found = find_url_credentials(text)
    assert {f.kind for f in found} == kinds
    assert holds_url_credentials(text) is bool(kinds - {"weak"})


def test_a_finding_never_shows_its_view() -> None:
    """``repr`` and ``str`` of a finding, alone or in a tuple, leave out the
    credential it holds."""
    found = find_url_credentials("https://u:S3CRET@h.example/x")
    assert found and found[0].view == "https://u:S3CRET@h.example/x"
    for text in (repr(found), str(found), repr(found[0]), str(found[0])):
        assert "S3CRET" not in text
    assert Finding("secret", "S3CRET", "***") == Finding("secret", "S3CRET", "***")


@pytest.mark.parametrize(
    "function", [find_url_credentials, holds_url_credentials], ids=["find", "holds"]
)
def test_the_defaults_read_an_account_name_and_no_id(
    function: Callable[..., object],
) -> None:
    """By default an ``ssh`` account name is a credential (not accepted),
    an scp address is looked for, and an id is not read percent-decoded
    nor after its first word."""
    assert function("ssh://git@h.example/r")
    assert function("alice:S3CRET@host.example:o/r")
    for text in (
        "urn:x:https:%2F%2Fu:S3CRET@h.example/x",
        "urn:x https://u:S3CRET@h.example/x",
    ):
        assert not function(text)
        assert function(text, embedded=True)


@pytest.mark.parametrize(
    ("url", "account", "kind", "weak"),
    [
        ("ssh://git@h.example/r", True, "account", True),
        ("ssh://git@h.example/r", False, "account", False),
        ("ssh://git@h.example/r", None, "account", False),
        ("https://git@h.example/r", True, "secret", False),
        ("ssh://npm_abc@h.example/r", True, "secret", False),
        ("ssh://hf_abc@h.example/r", True, "secret", False),
    ],
    ids=["accepted", "not-accepted", "default", "not-ssh", "npm-prefix", "hf-prefix"],
)
def test_an_account_name_is_weak_only_when_accepted(
    url: str, account: bool | None, kind: str, weak: bool
) -> None:
    """An account name on an ``ssh`` URL, with *account* (off by default),
    is weak; each side of that rule alone makes a credential, as does a
    token prefix."""
    if account is None:
        found = find_url_credentials(url)
    else:
        found = find_url_credentials(url, account=account)
    assert [(f.kind, f.weak) for f in found] == [(kind, weak)]


@pytest.mark.parametrize(
    "text",
    [
        "\ufeffhttps://u:S3CRET@h/x",
        "\u200bhttps://u:S3CRET@h/x",
        "https\u200b://u:S3CRET@h/x",
        "<https://u:S3CRET@h/x>",
        '"https://u:S3CRET@h/x"',
        " 'https://u:S3CRET@h/x' ",
        "x @ https://u:S3CRET@h/x --hash=sha256:abc",
        "htt\tps://u:S3CRET@h/x",
        "https://u:S3C\nRET@h/x",
        "\x01https://u:S3CRET@h/x",
        " \x02 https://u:S3CRET@h/x",
    ],
    ids=[
        *("bom", "zero-width", "zero-width-in-scheme", "angle", "quote"),
        *("squote", "hash", "tab-in-scheme", "line-feed-in-password"),
        *("leading-c0", "leading-c0-and-space"),
    ],
)
def test_a_value_is_read_as_a_reader_reads_it(text: str) -> None:
    """A format character (dropped by a reader), one enclosing pair and a
    requirement line's trailing words hide no credential; the masker hides
    it too, in a value and in a line."""
    found = find_url_credentials(text)
    assert [f.kind for f in found] == ["secret"]
    assert not any("S3CRET" in f.shown for f in found)
    # A value read once normalised is held as written.
    assert found[0].view == (text if "@ " not in text else "https://u:S3CRET@h/x")
    for line in (False, True):
        assert "S3CRET" not in masked_given_path(text, line=line)


def test_a_format_character_is_kept_where_it_hides_no_credential() -> None:
    """A bidirectional override stays in a masked message, so a quoting of it
    can still show it."""
    assert masked_given_path("a\u202eb https://h/x") == "a\u202eb https://h/x"


def test_a_value_is_read_as_urllib_reads_it() -> None:
    """The reading of :func:`test_a_value_is_read_as_a_reader_reads_it`
    follows ``urllib`` on this interpreter: a tab, CR or LF anywhere and a
    C0 control or space at the start are dropped; DEL is not, but a URL in
    the first word is read all the same
    (:func:`test_a_url_in_the_first_word_is_read`)."""
    from urllib.parse import urlsplit  # pylint: disable=import-outside-toplevel

    for text in ("htt\tps://u:p@h/", "https://u:p\r\n@h/", "\x01 \x1fhttps://u:p@h/"):
        assert urlsplit(text).password == "p"
        assert find_url_credentials(text)
    assert urlsplit("\x7fhttps://u:p@h/").password is None
    assert find_url_credentials("\x7fhttps://u:p@h/")


@pytest.mark.parametrize(
    ("text", "shown"),
    [
        (
            "https://spdx.org/spdxdocs/https:%2F%2Fu:S3CRET@h.example%2Fd.csv-1#P",
            "https://spdx.org/spdxdocs/https://***:***@h.example/d.csv-1#P",
        ),
        ("urn:x:hf:%2F%2Fd%2Fo%3Ftoken=S3CRET", "urn:x:hf://d/o?token=***"),
        ("urn:x:s3:%252F%252Fu:S3CRET@b", "urn:x:s3://***:***@b"),
    ],
    ids=["https", "query", "twice"],
)
def test_an_id_is_read_percent_decoded_and_masked_so(text: str, shown: str) -> None:
    """An id built from a name percent-encodes its ``/`` and ``?``: as an
    identifier it is read at each decode depth, and the masker shows the
    decoded text masked; a URL field is not read so."""
    assert [f.kind for f in find_url_credentials(text, embedded=True)] == ["secret"]
    assert not find_url_credentials(text)
    for line in (False, True):
        assert masked_given_path(text, line=line) == shown


def test_a_percent_encoded_text_without_a_credential_is_shown_as_given() -> None:
    text = "https://u:S3CRET@h/a%20b and urn:x:a%2Fb"
    assert (
        masked_given_path(text, line=True) == "https://***:***@h/a%20b and urn:x:a%2Fb"
    )


#: What may stand before a value in its first word without starting it:
#: ASCII punctuation (``"``, ``'`` and ``<`` enclose, ``+``, ``-`` and
#: ``.`` start a scheme's run), controls, Unicode letters, marks, digits
#: and format characters, and Unicode spaces (stripped at the start only).
_LEADS = [
    *"!#$%&()*,/:;=>?@[\\]^_`{|}~",
    *("!!(", "\x00", "\x1f", "\x7f", "\x80", "\x85", "\x9f"),
    *("\xa0", "\u3000", "\u00e9", "\u00df", "\u03b1", "\u6f22", "\u0661"),
    *("\u0301", "\uff48", "\u200b", "\ufeff", "\u00ad", "\ufeff!"),
]


@pytest.mark.parametrize(
    "lead", _LEADS, ids=["-".join(f"{ord(c):04X}" for c in lead) for lead in _LEADS]
)
def test_a_url_in_the_first_word_is_read(lead: str) -> None:
    """A credential URL behind a character that may not start it is found
    as a whole value, in a requirement and in a PURL qualifier, and the
    finding shows no secret; the same URL without one is no finding. (A
    ``&`` ends a PURL qualifier: a qualifier with no ``=`` is not read.)"""
    values = [
        (f"{lead}https://u:S3CRET@h.example/x", "secret"),
        (f"x @ {lead}https://u:S3CRET@h.example/x.whl", "secret"),
        (f"{lead}https://h.example/x?token=S3CRET", "secret"),
        (f"{lead}git+ssh://git@h.example/r", "account"),
    ]
    if lead != "&":
        purl = f"pkg:pypi/x?repository_url={lead}https://u:S3CRET@h.example/x"
        values.append((purl, "secret"))
    for value, kind in values:
        found = find_url_credentials(value, account=True)
        assert kind in {f.kind for f in found}, value
        assert not any("S3CRET" in f.shown for f in found)
        assert "S3CRET" not in masked_given_path(value)
    for clean in (f"{lead}https://h.example/x", f"{lead}https://h.example/a@b"):
        assert not find_url_credentials(clean, account=True)


_ADDRESS = "alice:S3CRET@host.example"
_ADDRESS_SHOWN = "***:***@host.example"


@pytest.mark.parametrize(
    ("text", "shown"),
    [
        ("!pkg:pypi/x?token=S3CRET", [("secret", "token=***")]),
        ("?pkg:pypi/x?token=S3CRET", [("secret", "token=***")]),
        ("pkg:/x?token=S3CRET", [("secret", "token=***")]),
        (f"(pkg:pypi/x@1#{_ADDRESS}:o/r", [("scp", f"{_ADDRESS_SHOWN}:o/r")]),
        (f"!{_ADDRESS}:o/r", [("scp", f"!{_ADDRESS_SHOWN}:o/r")]),
        (
            f",{_ADDRESS}:o/r,b:T0KEN@ee:f",
            [("scp", f",{_ADDRESS_SHOWN}:o/r,***:***@ee:f")],
        ),
        (f"{_ADDRESS}:o/pkg:x", [("scp", f"{_ADDRESS_SHOWN}:o/pkg:x")]),
        (f"{_ADDRESS}:pkg:x", [("scp", f"{_ADDRESS_SHOWN}:pkg:x")]),
        (
            "!https://u:S3CRET@h/a,b:c@dd:e",
            [("secret", "https://***:***@h/a,***:***@dd:e")],
        ),
        (
            "https://h/x?next=alice%3AS3CRET%40host%3A%2Fsrv%2Fr",
            [("scp", "https://h/x?next=***:***@host:/srv/r")],
        ),
        (
            "Docs:https://u:S3CRET@h.example/x",
            [("secret", "https://***:***@h.example/x")],
        ),
        (
            "urn:x:https://u:S3CRET@h.example/x",
            [("secret", "https://***:***@h.example/x")],
        ),
        (
            "!https://h.example/x see https://u:S3CRET@h2.example/y",
            [("secret", "https://***:***@h2.example/y")],
        ),
    ],
    ids=[
        *("purl", "purl-after-mark", "purl-url-tie", "purl-subpath", "scp"),
        *("scp-run", "scp-path-pkg", "scp-before-pkg", "url-before-scp"),
        *("decoded-scp", "after-a-word", "in-an-urn", "whole-after-the-first"),
    ],
)
def test_each_kind_starts_in_the_first_word(
    text: str, shown: list[tuple[str, str]]
) -> None:
    """A PURL, an scp-style address and a URL are read from where they start
    in the first word, as the masker reads them, the earliest deciding (a
    PURL on a tie with a URL); a value whose first word holds a URL is read
    whole."""
    assert [(f.kind, f.shown) for f in find_url_credentials(text)] == shown


@pytest.mark.parametrize(
    "text",
    [
        "see !https://u:S3CRET@h.example/x",
        "see pkg:pypi/x?token=S3CRET",
        "Apkg:pypi/x?token=S3CRET",
        "https://h/pkg:pypi/x?token=S3CRET#",
        "alice:pw@host:/srv/r",
    ],
    ids=["second-word", "purl-second-word", "purl-after-a-letter"]
    + ["purl-in-a-url", "address-path"],
)
def test_the_first_word_decides_what_a_value_is(text: str) -> None:
    """The finder's prose ruling: a value after white space is prose; a
    ``pkg:`` after a letter is no PURL, as for the masker; a ``pkg:`` after
    a URL's start is part of the URL (its ``token`` a secret parameter
    there); an scp-style address whose path looks like a URL is an
    address."""
    found = find_url_credentials(text)
    if text.startswith("see"):
        assert not found
    elif text.startswith("A"):
        assert not found and masked_given_path(text) == text
    elif text.startswith("https"):
        assert [(f.kind, f.view) for f in found] == [("secret", text)]
    else:
        assert [f.kind for f in found] == ["scp"]


def test_only_what_urllib_strips_leads_a_normalised_value() -> None:
    """``normalised`` strips a C0 control or a space at the start, no more:
    a ``!`` is part of the value (the first-word reading skips it)."""
    assert normalised("\x00 \x20x") == "x"
    assert normalised("!x") == "!x"
    assert normalised("\x01!x") == "!x"


@pytest.mark.parametrize(
    ("text", "shown"),
    [
        ("a:b@cc:https://u:S3CRET@h/x", "https://***:***@h/x"),
        ("a:b@cc:pkg:pypi/x?token=S3CRET", "token=***"),
    ],
    ids=["url", "purl"],
)
def test_an_address_decides_nothing_when_none_is_looked_for(
    text: str, shown: str
) -> None:
    """With *scp* false (a file name), an scp-style address in front of a
    URL or a PURL does not hide it."""
    assert [(f.kind, f.shown) for f in find_url_credentials(text, scp=False)] == [
        ("secret", shown)
    ]
