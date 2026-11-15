# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The credential detector (:func:`pitloom.core.url_masking.find_url_credentials`):
a URL-typed value read as a whole, never prose; no weaker than the retired
SBOM strip on such values; never showing what it finds; the masker hiding
all it refuses; weak names told and not refused.

See also: _probe_corpus.py (the corpus), test_url_masking_hits.py (each
kind of value and 1 MiB timings), test_url_masking_tokens.py (token shapes),
test_url_masking_mask.py (the masker) and test_url_masking_credentials.py
(the refusal surfaces) in this folder.
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
    ],
    ids=[
        *("bom", "zero-width", "zero-width-in-scheme", "angle", "quote"),
        *("squote", "hash"),
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
