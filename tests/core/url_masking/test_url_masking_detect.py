# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The credential detector (:func:`pitloom.core.url_masking.find_url_credentials`):
a URL-typed value read as a whole, never prose; no weaker than the retired
SBOM strip on such values; never showing what it finds; the masker hiding
all it refuses; weak names told and not refused.

See also: _probe_corpus.py (the corpus), test_url_masking_detect_shapes.py
(token shapes and 1 MiB timings) and test_url_masking_credentials.py (the
refusal surfaces) in this folder.
"""

from __future__ import annotations

import inspect

import pytest

from pitloom.core.url_masking import (
    Finding,
    find_url_credentials,
    holds_url_credentials,
    masked_given_path,
)
from tests.core.url_masking._probe_corpus import PLANTED, PROBES, encoded, marks


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
        ("build:42@ci:linux now", set()),
        ("", set()),
    ],
    ids=[
        *("weak", "weak-in-weak", "secret-in-weak", "space-path", "space-user"),
        *("requirement", "requirement-account", "requirement-scp"),
        *("one-letter-scheme", "drive", "scp"),
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
    ("url", "account", "kind", "weak"),
    [
        ("ssh://git@h.example/r", True, "account", True),
        ("ssh://git@h.example/r", False, "account", False),
        ("https://git@h.example/r", True, "secret", False),
        ("ssh://npm_abc@h.example/r", True, "secret", False),
        ("ssh://hf_abc@h.example/r", True, "secret", False),
    ],
    ids=["accepted", "not-accepted", "not-ssh", "npm-prefix", "hf-prefix"],
)
def test_an_account_name_is_weak_only_when_accepted(
    url: str, account: bool, kind: str, weak: bool
) -> None:
    """An account name on an ``ssh`` URL, with *account*, is weak; each side
    of that rule alone makes a credential, as does a token prefix."""
    found = find_url_credentials(url, account=account)
    assert [(f.kind, f.weak) for f in found] == [(kind, weak)]


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


@pytest.mark.parametrize(
    "text",
    ["pkg:pypi/x@1.0", "see pkg:pypi/x@1.0#sub ok", "pkg:generic/x?checksum=sha256:ab"],
    ids=["no-qualifier", "subpath-in-prose", "clean-qualifier"],
)
def test_a_purl_without_a_hit_is_masked_as_given(text: str) -> None:
    assert masked_given_path(text) == text
