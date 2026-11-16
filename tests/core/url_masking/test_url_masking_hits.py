# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""What the detector reads in a URL-typed value
(:mod:`pitloom.core.url_masking._hits`): scp-style addresses, nested
queries, PURL qualifiers at each decode depth, PEP 508 requirements, and
each view's time on adversarial 1 MiB texts.

See also: test_url_masking_detect.py (the detector) and
test_url_masking_tokens.py (token shapes) in this folder.
"""

from __future__ import annotations

import functools
import sys
import time
from collections.abc import Callable

import pytest

from pitloom.core.url_masking import find_url_credentials, masked_given_path
from tests.core.url_masking._probe_corpus import PLANTED, encoded, marks


@pytest.mark.parametrize("scp", [True, False], ids=["scp", "no-scp"])
def test_an_scp_address_is_looked_for_only_when_asked(scp: bool) -> None:
    found = find_url_credentials("alice:S3CRET@host.example:o/r", scp=scp)
    assert [(f.kind, f.shown) for f in found] == (
        [("scp", "***:***@host.example:o/r")] if scp else []
    )


@pytest.mark.parametrize(
    "text",
    [",a:S3CRET@cc:d,b:T0KEN@ee:f", "a:S3CRET@cc:d b:T0KEN@ee:f", "x a:S3CRET@cc:d"],
    ids=["comma-run", "two-words", "sentence"],
)
def test_text_holding_scp_addresses_is_no_address(text: str) -> None:
    """Only a value that is one address, with no white space, is one."""
    assert not find_url_credentials(text)


@pytest.mark.parametrize(
    ("text", "kinds"),
    [
        (marks(15), []),
        (marks(16), []),
        (marks(17), ["nesting"]),
        ("https://h/x?code=1" + "?q=1" * 16, ["weak"]),
        ("https://h/x?token=1" + "?q=1" * 16, ["secret"]),
        ("https://h/x?code=1" + "?q=1" * 17, ["nesting"]),
    ],
    ids=["15", "16", "17", "weak-16", "secret-16", "weak-17"],
)
def test_a_value_nested_over_sixteen_marks_is_found(
    text: str, kinds: list[str]
) -> None:
    """A value holding 16 ``?`` is read as its name says; 17 is nesting."""
    assert [f.kind for f in find_url_credentials(text)] == kinds


_PURL = "pkg:generic/x?checksum=sha256:ab&download_url="


@pytest.mark.parametrize(
    ("value", "kinds"),
    [
        (encoded("https://u:S3CRET@h.example/x", 0), ["secret"]),
        (encoded("https://u:S3CRET@h.example/x", 1), ["secret"]),
        (encoded("https://u:S3CRET@h.example/x", 5), ["secret"]),
        (encoded("https://u:S3CRET@h.example/x", 6), ["nesting"]),
        (encoded('https://h.example/x"?token=T0KEN', 1), ["secret"]),
        (encoded("https://h.example/x?a=1", 5), []),
    ],
    ids=["plain", "once", "five", "six", "field-reading", "clean"],
)
def test_a_purl_qualifier_is_read_at_every_decode_depth(
    value: str, kinds: list[str]
) -> None:
    """A qualifier value is read as written and after each of five decodes,
    as one URL when it is one (a quote does not end it); one still encoded
    after the fifth is nesting, shown as its key only."""
    found = find_url_credentials(_PURL + value)
    assert [f.kind for f in found] == kinds
    assert not any(s in f.shown for f in found for s in PLANTED)
    if kinds == ["nesting"]:
        assert found[0].shown == "download_url=***"


@pytest.mark.parametrize("prefix", ["pkg", "PKG", "Pkg"])
def test_a_purl_is_known_in_any_case(prefix: str) -> None:
    text = f"{prefix}:generic/x?u=" + encoded("https://u:S3CRET@h.example/x", 1)
    assert [f.kind for f in find_url_credentials(text)] == ["secret"]
    assert "S3CRET" not in masked_given_path(text)


#: Requirement strings, each a whole value, with a credential in the URL of
#: its direct reference.
_REQUIREMENTS = [
    "n @ https://u:S3CRET@h.example/x.whl",
    "n@https://u:S3CRET@h.example/x.whl",
    "n.a-b_c @ https://u:S3CRET@h.example/x.whl",
    "n[a,b] @ https://u:S3CRET@h.example/x.whl",
    "n [a] @ https://u:S3CRET@h.example/x.whl",
    "n  @  git+ssh://u:S3CRET@h.example/r",
    'n @ https://h.example/x.whl?token=T0KEN ; python_version>"3"',
    "n @ https://o'brien:S3CRET@h.example/x.whl",
    "n @ https://u:S3CRET@h.example/x.whl,",
    "n @ s3:/u:S3CRET@h.example/x",
]


@pytest.mark.parametrize("text", _REQUIREMENTS)
def test_a_requirement_with_a_credential_in_its_url_is_refused(text: str) -> None:
    """A value that is one requirement (extras, no space around ``@``, a
    marker, a quote in the user information, a trailing comma, a scheme
    after one ``/``) is refused, and neither a finding nor the masker shows
    the credential."""
    found = find_url_credentials(text)
    assert any(not f.weak for f in found), text
    shown = masked_given_path(text) + "".join(f.shown for f in found)
    assert not any(secret in shown for secret in PLANTED), text


@pytest.mark.parametrize(
    ("text", "kinds"),
    [
        (" \tpkg:g/x@1?u=https://u:S3CRET@h/x\n", ["secret"]),
        ("  alice:S3CRET@host:repo ", ["scp"]),
        ("\nhttps://u:S3CRET@h/x ", ["secret"]),
        ("n @ https://h/x?token=S3CRET #c", ["secret"]),
        ("n @ https://h/x;token=S3CRET", ["secret"]),
        ("pkg:g/x@1?download_url=https://h/x?a=1&token=S3CRET", ["secret"]),
        ("pkg:g/x@1?download_url=https://h/x#token=S3CRET", ["secret"]),
        ("pkg:g/x@1?password=S3CRET", ["secret"]),
        ("pkg:g/x@1?code=abc", ["weak"]),
        ("pkg:g/x@1?token=", []),
        ("pkg:g/x@1?u=%20https://u:S3CRET@h/x", ["secret"]),
        ("https://h/x see https://u:S3CRET@h2/y", ["secret"]),
        ("alice:S3CRET@host:o/r trailing", []),
        ("see https://u:S3CRET@h/x", []),
    ],
    ids=[
        *("space-purl", "space-scp", "space-url", "requirement-comment"),
        *("requirement-semicolon", "qualifier-token", "subpath-token"),
        *("qualifier-password", "qualifier-weak", "qualifier-empty"),
        *("decoded-space", "url-then-words", "scp-then-words", "words-then-url"),
    ],
)
def test_a_value_is_read_whole_whatever_surrounds_or_splits_it(
    text: str, kinds: list[str]
) -> None:
    """White space around a value (decoded too), a requirement's comment
    and a PURL qualifier named like a secret (written plainly, as its own
    pair, or in the fragment of a URL value) do not hide a credential; a
    qualifier named like a secret shows its key only. A value starting with
    a URL is read whole, white space and later URLs included; an scp-style
    address followed by words, or words before a URL, is prose."""
    found = find_url_credentials(text)
    assert [f.kind for f in found] == kinds
    assert not any("S3CRET" in f.shown for f in found)


_GHP = "ghp_T0KEN" + "aB3" * 10 + "x"
_SCP = "alice:S3CRET@host:o/r"


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("https://h/x?next=https://u:S3CRET@h2/y", "secret"),
        (f"https://h/x?next={_SCP}", "scp"),
        (f"https://h/x?a=1&next={_SCP}#f", "scp"),
        (f"https://h/x?next={_GHP}", "token"),
        ("pkg:g/x?u=https://u:S3CRET@h2/y", "secret"),
        (f"pkg:g/x?vcs_url={_SCP}", "scp"),
        (f"pkg:g/x?note={_GHP}", "token"),
        (f"pkg:g/x?u=https://h/x?next={_SCP}", "scp"),
        ("pkg:pypi/x@1?a=b#sub/https://u:S3CRET@h", "secret"),
        ("pkg:pypi/x@1#sub/https://u:S3CRET@h", "secret"),
        ("pkg:pypi/x@1?a=b#u:S3CRET@h:x", "scp"),
        (f"pkg:pypi/x@1#sub/{_GHP}", "token"),
        ("pkg:pypi/x@1#" + encoded("sub/https://u:S3CRET@h", 2), "secret"),
        ("pkg:pypi/x@1#" + encoded("https://u:S3CRET@h", 6), "nesting"),
        ("pkg:pypi/x@1#%20u:S3CRET@h:x", "scp"),
    ],
    ids=[
        *("url-url", "url-scp", "url-scp-mid", "url-token"),
        *("purl-url", "purl-scp", "purl-token", "purl-url-scp"),
        *("subpath-url", "subpath-bare", "subpath-scp", "subpath-token"),
        *("subpath-encoded", "subpath-nesting", "subpath-decoded-space"),
    ],
)
def test_a_nested_value_is_read_in_every_container(text: str, kind: str) -> None:
    """A URL, an scp-style address or a token nested in a URL's query, a
    PURL qualifier or a PURL subpath (as written or encoded) is found, and
    the masker hides it."""
    found = find_url_credentials(text)
    assert [f.kind for f in found] == [kind]
    assert "S3CRET" not in masked_given_path(text)
    assert _GHP[4:] not in masked_given_path(text)
    assert not any("S3CRET" in f.shown or _GHP[4:] in f.shown for f in found)


@pytest.mark.parametrize(
    "text",
    [
        "urn:x:https://u:S3CRET@h/x",
        "src/https:/u:S3CRET@h/x",
        "pkg:g/x?note=see%20https%3A%2F%2Fu%3AS3CRET%40h",
        "pkg:pypi/x@1#sub/x",
    ],
    ids=["urn", "file-key", "qualifier-prose", "clean-subpath"],
)
def test_a_url_inside_a_value_of_no_kind_is_not_read(text: str) -> None:
    """Accepted by the whole-value ruling: a URL inside a value that is no
    URL, requirement, scp-style address or PURL, or inside a PURL qualifier
    value that is prose, is not found."""
    assert not find_url_credentials(text)


def _measured() -> bool:
    """Whether a coverage tracer runs (``sys.settrace``, or coverage's
    ``sys.monitoring`` core, the default on Python 3.14), which slows the
    scanners' loops many times over."""
    if sys.gettrace() is not None:
        return True
    coverage = sys.modules.get("coverage")
    return coverage is not None and coverage.Coverage.current() is not None


_COVERED = _measured()
#: Each adversarial shape, at about *n* characters. Every shape that once
#: found a quadratic scan is kept (white space for the requirement pattern,
#: ``,a:b@cc:d`` scp runs, many ``?``, one-slash schemes, a deep PURL).
_SHAPES: dict[str, Callable[[int], str]] = {
    "late-scheme": lambda n: "a" * n + "://",
    "late-at": lambda n: "https://u:" + "a" * n + "@",
    "wide": lambda n: "s3:/" * (n // 8) + "ab:\\" * (n // 8),
    "many-marks": lambda n: "https://h/x?q=" + "1?" * (n // 2),
    "many-secrets": lambda n: "https://h/x?" + "token=a&" * (n // 8),
    "purl-deep": lambda n: "pkg:generic/x?u=" + "%25" * (n // 3),
    "purl-many": lambda n: "pkg:generic/x?" + "u=https%3A%2F%2F&" * (n // 17),
    "tokens": lambda n: "ghp_" * (n // 8) + "hf_" + "a" * (n // 2),
    "references": lambda n: "@a:/" * (n // 8) + "@ " * (n // 4) + " " * (n // 4),
    "scp": lambda n: ",a:b@cc:d" * (n // 18) + "a:b@" * (n // 8) + "a:" * (n // 4),
    "scp-value": lambda n: "a:b@cc:" + "d" * n,
    "requirement": lambda n: "n" * (n // 3) + " @ " + "@ " * (n // 6) + "[" * (n // 3),
    "requirement-space": lambda n: "a" + " " * n + "x",
    "requirement-bracket": lambda n: "a" + " " * (n // 2) + "[" + " " * (n // 2),
    "requirement-extras": lambda n: "a [" + "x " * (n // 2),
    "subpath": lambda n: "pkg:x/y#" + "s3:/" * (n // 8) + "a:b@" * (n // 8),
    "query-scp": lambda n: "https://h/x?" + "a=b:c@d:e&" * (n // 10),
    "format": lambda n: "\u200b" * (n // 2) + "https://u:p@h" + "\ufeff" * (n // 2),
    "enclosed": lambda n: "<" * (n // 2) + "https://h" + ">" * (n // 2),
    "semicolons": lambda n: "https://h/x?token=" + ";" * n + "&a=1",
    "path-parameters": lambda n: "https://h/x" + ";sid=a" * (n // 6),
    "tabs": lambda n: "https://u:" + "\t" * (n // 2) + "@" + "\t@" * (n // 4),
    "openai": lambda n: "sk-proj-" + "a" * n + "T3BlbkFJ",
    "embedded": lambda n: "urn:x:" + "s3:/a" * (n // 5),
}


#: Each view of a text: the detector (a value, a PURL qualifier, an
#: identifier) and the masker (a value, a line).
_VIEWS: tuple[Callable[[str], object], ...] = (
    find_url_credentials,
    lambda text: find_url_credentials("pkg:x/y?u=" + text),
    lambda text: find_url_credentials(text, embedded=True),
    masked_given_path,
    lambda text: masked_given_path(text, line=True),
)


def _views(text: str) -> None:
    for view in _VIEWS:
        view(text)


def _timed(view: Callable[[str], object], text: str) -> float:
    started = time.perf_counter()
    view(text)
    return time.perf_counter() - started


@functools.cache
def _tick() -> float:
    """The step of the clock: what two readings differ by at least (100 ns
    on Windows' ``perf_counter``, 15.6 ms on a coarse clock)."""
    steps = []
    for _ in range(3):
        started = now = time.perf_counter()
        while now == started:
            now = time.perf_counter()
        steps.append(now - started)
    return min(steps)


#: The size factor between the two samples, and the growth a linear scan
#: stays well under (16 times the size: 16 times the time; a quadratic one
#: grows 256 times, one with a linear part as large still 136 times).
_FACTOR = 16
_GROWTH = 32
#: The least size, and the most, of the smaller sample.
_FIRST = 1 << 10
_LAST = 1 << 19


def _growth(view: Callable[[str], object], shape: Callable[[int], str]) -> float:
    """How many times longer *view* takes on *shape* at 16 times the size:
    the smaller size the first, from 1 KiB up by 4 times, whose one run
    takes 3 ms and 4 clock steps at least, so the clock reads it; 1.0 when
    even 512 KiB runs faster (no scan of that size is slow)."""
    floor = max(0.003, 4 * _tick())
    size = _FIRST
    while (small := _timed(view, shape(size))) < floor:
        if size >= _LAST:
            return 1.0
        size *= 4
    return _timed(view, shape(_FACTOR * size)) / small


@pytest.mark.parametrize("name", list(_SHAPES), ids=list(_SHAPES))
def test_each_view_is_linear(name: str) -> None:
    """For each view, 16 times the text takes about 16 times as long,
    never 256 (a quadratic scan), with the smaller text sized so that one
    run is measured (3 ms and 4 clock steps at least): the growth must stay
    under 32, the least of three tries, so a loaded machine or a coarse
    clock passes and a quadratic scan fails by twice the bound or more."""
    for view in _VIEWS:
        growth = _growth(view, _SHAPES[name])
        for _ in range(2):
            if growth < _GROWTH:
                break
            growth = min(growth, _growth(view, _SHAPES[name]))
        assert growth < _GROWTH, f"growth {growth:.1f}"


@pytest.mark.skipif(_COVERED, reason="a coverage tracer slows the scan many times")
@pytest.mark.parametrize("name", ["requirement-space", "scp"])
def test_a_mebibyte_ends_in_seconds(name: str) -> None:
    """The two shapes that once took minutes, at 1 MiB, end in seconds."""
    started = time.perf_counter()
    _views(_SHAPES[name](1 << 20))
    assert time.perf_counter() - started < 40
