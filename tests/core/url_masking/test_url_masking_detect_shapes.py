# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The access-token shapes of the credential detector and the masker, and
the detector's time on adversarial 1 MiB texts.

See also: test_url_masking_detect.py (the detector's readings) and
_probe_corpus.py (README prose that must not be refused) in this folder.
"""

from __future__ import annotations

import time

import pytest

from pitloom.core.url_masking import find_url_credentials, masked_given_path
from tests.core.url_masking._probe_corpus import b62

_HF = "Tq" * 17
#: Each prefix and a body of the shortest real shape.
_SHAPES = {
    **{f"gh{kind}_": b62(36) for kind in "porsu"},
    "github_pat_": f"{b62(22)}_{b62(59)}",
    **{f"{p}-": b62(20) for p in ("glpat", "gldt", "glptt", "glrt", "gloas")},
    "glcbt-": b62(20),
    **{f"xox{kind}-": f"1-2-{b62(8)}" for kind in "abeprs"},
    "xapp-": f"1-A0T0KEN1-1-{b62(8)}",
    "hf_": _HF,
    "api_org_": _HF,
    "AKIA": "T0KEN12345678901",
    "ASIA": "T0KEN12345678901",
    "pypi-": f"AgE{b62(50)}",
    "npm_": b62(36),
}


@pytest.mark.parametrize("prefix", list(_SHAPES), ids=list(_SHAPES))
def test_a_token_shape_in_a_url_value_is_found_and_masked(prefix: str) -> None:
    """A token of its shortest real shape is found in a URL value (a path
    segment, a query value, right after a percent-encoded character) and
    shown as its prefix; one character short or inside a longer word it is
    none, and so is any token in prose, which the masker still hides."""
    token = prefix + _SHAPES[prefix]
    body = token[len(prefix) :]
    for url in (f"https://h/{token}/x", f"https://h/x?q=Bearer%20{token}"):
        found = find_url_credentials(url)
        assert [(f.kind, f.shown) for f in found] == [("token", f"{prefix}***")]
        assert body not in masked_given_path(url)
    assert not find_url_credentials(f"https://h/{token[:-1]}/x")
    assert not find_url_credentials(f"https://h/x{token}/x")
    assert not find_url_credentials(f"set {token} now")
    assert body not in masked_given_path(f"set {token} now")


@pytest.mark.parametrize(
    "token",
    [f"ghp_{b62(37)}", f"npm_{b62(37)}", "AKIAT0KEN123456789012", f"hf_{_HF}x"],
    ids=["ghp-37", "npm-37", "akia-17", "hf-35"],
)
def test_a_token_of_a_fixed_length_is_none_when_longer(token: str) -> None:
    assert not find_url_credentials(f"https://h/{token}")


@pytest.mark.parametrize(
    "text",
    [
        *("github_pat_creation_instructions_page", "glpat-token-rotation-guide-v2"),
        *("xoxb-bot-token-scopes-explained", "xapp-config-reference-guide"),
        *("pypi-simple-index-mirror-configuration-for-enterprise-use",),
        *("hf_hub_download", "HF_HUB_ENABLE_HF_TRANSFER", "npm_config_registry"),
        *("api_org_settings_page", "ASIAPACIFICREGION1", "sk-" + "a1" * 24),
        *("glpat-" + "a1" * 10, "glpat-" + "A1" * 10, "hf_" + "t" * 34),
    ],
    ids=[
        *("pat-slug", "glpat-slug", "xoxb-slug", "xapp-slug", "pypi-slug"),
        *("hf-call", "hf-env", "npm-config", "api-org-slug", "asia-word", "sk"),
        *("glpat-no-upper", "glpat-no-lower", "hf-no-upper"),
    ],
)
def test_a_slug_in_a_url_is_no_token(text: str) -> None:
    """A slug, an environment variable or a body missing what a random draw
    holds (a digit, an upper- and a lower-case letter) is no token, in a
    URL's path or in a message."""
    assert not find_url_credentials(f"https://docs.example/{text}")
    assert masked_given_path(text) == text


_MIB = 1 << 20
_LARGE = {
    "late-scheme": "a" * _MIB + "://",
    "late-at": "https://u:" + "a" * _MIB + "@",
    "wide": "s3:/" * (_MIB // 4) + "ab:\\" * (_MIB // 4),
    "many-marks": "https://h/x?q=" + "1?" * (_MIB // 2),
    "many-secrets": "https://h/x?" + "token=a&" * (_MIB // 8),
    "purl-deep": "pkg:generic/x?u=" + "%25" * (_MIB // 3),
    "purl-many": "pkg:generic/x?" + "u=https%3A%2F%2F&" * (_MIB // 17),
    "tokens": "ghp_" * (_MIB // 4) + "hf_" + "a" * _MIB + "%20glpat-" * (_MIB // 9),
    "references": "@a:/" * (_MIB // 4) + "@ " * (_MIB // 2) + "@" + " " * _MIB,
    "scp": ",a:b@cc:d" * (_MIB // 9) + "a:b@" * (_MIB // 4) + "a:" * (_MIB // 2),
    "scp-value": "a:b@cc:" + "d" * _MIB,
    "requirement": "n" * _MIB + " @ " + "@ " * (_MIB // 2) + "[" * _MIB,
}


@pytest.mark.parametrize("name", list(_LARGE), ids=list(_LARGE))
def test_each_view_is_linear_on_a_mebibyte(name: str) -> None:
    """Each view's scan, and the masker, of an adversarial 1 MiB text end in
    seconds (a quadratic one takes hours)."""
    started = time.monotonic()
    find_url_credentials(_LARGE[name])
    find_url_credentials("pkg:x/y?u=" + _LARGE[name])
    masked_given_path(_LARGE[name])
    assert time.monotonic() - started < 20
