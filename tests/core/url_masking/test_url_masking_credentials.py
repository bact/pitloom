# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A secret planted in a URL is masked by every sink that writes text (the
log formatter, a traceback, ``KEY=VALUE`` stdout), removed by the SBOM strip
and read as one rule by the masker, the strip and the refusal of a stored
value.

See also: test_url_masking_userinfo.py, test_url_masking_strip.py and
test_url_masking_given_path.py in this folder.
"""

from __future__ import annotations

import json

import pytest

from pitloom.cli.kv_output import kv_line
from pitloom.core.iri import require_namespace_iri
from pitloom.core.url_masking import (
    holds_url_credentials,
    masked_given_path,
    strip_url_secrets,
)
from pitloom.logging_config import escape_controls, print_traceback

pytestmark = pytest.mark.platform

SECRET = "PLANTSECRET"
_SHAPES = [
    f"https://u:{SECRET}@once.example/p",
    f"https://h/p?token={SECRET}",
    f"https://h/p?code={SECRET}&session={SECRET}&ticket={SECRET}",
    f"https://h/p?token%3D={SECRET}",
    f"alice:{SECRET}@host:o/r",
]
_IDS = ["userinfo", "token", "code-session-ticket", "encoded-name", "scp-password"]


@pytest.mark.parametrize("shape", _SHAPES, ids=_IDS)
def test_every_sink_masks_a_secret_the_caller_forgot(
    shape: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """The formatter's escape, a traceback line and a ``KEY=VALUE`` value
    mask a URL whatever site wrote it; stdout data keeps scp-style text."""
    assert SECRET not in escape_controls(f"failed on {shape}")
    if shape in _SHAPES[:4]:
        assert SECRET not in kv_line(PATH=shape)
    try:
        raise ValueError(f"cannot read {shape}")
    except ValueError:
        print_traceback()
    assert SECRET not in capsys.readouterr().err


@pytest.mark.parametrize(
    "shape", _SHAPES[:2] + _SHAPES[3:4], ids=["userinfo", "token", "encoded-name"]
)
def test_the_stripped_url_keeps_what_is_not_secret(shape: str) -> None:
    plain, changed = strip_url_secrets(f"see {shape}, ok")
    assert SECRET not in plain and plain.startswith("see ") and changed
    assert SECRET not in "".join(changed)


@pytest.mark.parametrize(
    ("text", "plain"),
    [
        ("https://u:p@h/x?token=T&a=1", "https://h/x?a=1"),
        ("https://h/x?a=1&key=K", "https://h/x?a=1"),
        ("https://h/x?token=T&b=2&sig=S", "https://h/x?b=2"),
        ("https://h/x?token=T", "https://h/x"),
        ("https://h/p?x=1#frag", "https://h/p?x=1#frag"),
        ("foo @ https://u:p@h/x.whl#sig=Q", "foo @ https://h/x.whl"),
        ("https://h/p?token=T#frag", "https://h/p#frag"),
        ('{"n":"https://h/x?token=T"}', '{"n":"https://h/x"}'),
        ("https://h/x#access_token=x&state=y", "https://h/x#state=y"),
        ("https://h/x?accesstoken=Z&a=1", "https://h/x?a=1"),
        ("https://h/x?a=1#sig=Q", "https://h/x?a=1"),
        (
            "https://h/x?tokenizer=bert&max_tokens=3",
            "https://h/x?tokenizer=bert&max_tokens=3",
        ),
    ],
)
def test_a_secret_parameter_is_dropped_whole(text: str, plain: str) -> None:
    """A fragment stays a fragment and a joined name is a secret."""
    assert strip_url_secrets(text)[0] == plain
    assert not strip_url_secrets(plain)[1]  # idempotent, nothing to report


@pytest.mark.parametrize(
    "text",
    [
        "ssh://git@github.com/o/r.git",
        "git+ssh://git@github.com/o/r.git@main",
        "https://h/x?code=utf8&country_code=TH&session=2024",
        "https://docs.example?contact=me@x.org",
        "python:3.11@sha256:deadbeef and sip:alice@example.org:5060",
    ],
)
def test_the_sbom_strip_leaves_what_is_no_credential(text: str) -> None:
    assert strip_url_secrets(text) == (text, [])


def test_the_provenance_json_of_a_stripped_url_still_parses() -> None:
    note = json.dumps({"note": f"foo @ https://a:{SECRET}@h/x.whl?token={SECRET}"})
    plain, changed = strip_url_secrets(note)
    assert json.loads(plain) == {"note": "foo @ https://h/x.whl"} and changed
    assert SECRET not in "".join(changed)


@pytest.mark.parametrize(
    "text",
    [
        "C:\\a\\b.txt",
        "a@b.org: bad",
        "https://h:80/x",
        "key=value",
        "node:20@SHA256:abc",
    ],
    ids=["drive-path", "address", "port", "pair", "digest"],
)
def test_an_ordinary_path_and_address_stay_as_they_are(text: str) -> None:
    assert masked_given_path(text, line=True) == text


@pytest.mark.parametrize(
    "text",
    ["python:3.11@sha256:deadbeef", "C:\\a@b:c", "ns:x@y"],
    ids=["image", "drive", "one-colon"],
)
def test_no_credential_is_found_in_an_image_reference_or_a_drive(text: str) -> None:
    assert not holds_url_credentials(text)
    assert masked_given_path(text) == text


@pytest.mark.parametrize(
    "url",
    [
        f"https://u:pa?{SECRET}@h/ns",
        f"https://u:pa#{SECRET}@h/ns",
        f"https://u:{SECRET}@h/ns",
        f"https://{SECRET}@h/ns",
        f"https://u%40x:{SECRET}@h/ns",
    ],
    ids=["question", "hash", "plain", "user-only", "percent-at"],
)
def test_masker_strip_hold_and_refusal_agree(url: str) -> None:
    """One definition of user information: where the masker masks, the strip
    removes, ``holds_url_credentials`` says so, and a namespace is refused."""
    assert SECRET not in masked_given_path(url)
    plain, changed = strip_url_secrets(url)
    assert SECRET not in plain and changed
    assert holds_url_credentials(url)
    with pytest.raises(ValueError):
        require_namespace_iri(url)
