# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A secret planted in a URL is masked by every sink that writes text (the
log formatter, a traceback, ``KEY=VALUE`` stdout), and read as one rule by
the masker and the refusal of a stored value.

See also: test_url_masking_userinfo.py, test_url_masking_detect.py and
test_url_masking_given_path.py in this folder.
"""

from __future__ import annotations

import pytest

from pitloom.cli.kv_output import kv_line
from pitloom.core.iri import require_namespace_iri
from pitloom.core.url_masking import holds_url_credentials, masked_given_path
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
    "text",
    [
        "ssh://git@github.com/o/r.git",
        "git+ssh://git@github.com/o/r.git@main",
        "https://h/x?code=utf8&country_code=TH&session=2024",
        "https://docs.example?contact=me@x.org",
        "python:3.11@sha256:deadbeef and sip:alice@example.org:5060",
    ],
)
def test_what_is_no_credential_is_not_refused(text: str) -> None:
    assert not holds_url_credentials(text, account=True)


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
def test_masker_hold_and_refusal_agree(url: str) -> None:
    """One definition of user information: where the masker masks,
    ``holds_url_credentials`` says so, and a namespace is refused."""
    assert SECRET not in masked_given_path(url)
    assert holds_url_credentials(url)
    with pytest.raises(ValueError):
        require_namespace_iri(url)
