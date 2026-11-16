# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The access-token shapes (:mod:`pitloom.core.url_masking._tokens`) the
detector finds in a URL value and the masker hides anywhere.

See also: test_url_masking_hits.py (the detector's readings) and
_probe_corpus.py (README prose that must not be refused) in this folder.
"""

from __future__ import annotations

import pytest

from pitloom.core.url_masking import find_url_credentials, masked_given_path
from tests.core.url_masking._probe_corpus import TOKENS, b62

#: The shapes whose body runs on past its shortest length.
_OPEN = (
    *("glpat-", "gldt-", "glrt-", "glcbt-", "gloas-", "xapp-", "pypi-"),
    *(f"xox{kind}-" for kind in "abeoprs"),
    *("xoxe.xoxb-", "xoxe.xoxp-"),
)
_IN_URL = "https://h.example/x?q="
#: The token rows of the probe corpus at a8425fb5 (before the gitleaks
#: shapes), as written there; ``b62`` is unchanged in its first 95.
_EARLIER = {
    **{f"gh{k}": f"gh{k}_{b62(36)}" for k in "porsu"},
    "github-pat": f"github_pat_{b62(22)}_{b62(59)}",
    **{p: f"{p}-{b62(20)}" for p in ("glpat", "gldt", "glptt", "glrt")},
    **{p: f"{p}-{b62(20)}" for p in ("gloas", "glcbt")},
    **{f"xox{k}": f"xox{k}-1-2-{b62(24)}" for k in "abeprs"},
    "xapp": f"xapp-1-A0T0KEN12-1234567890-{b62(16)}",
    "hf": f"hf_{'Tq' * 17}",
    "api-org": f"api_org_{'Tq' * 17}",
    "pypi": f"pypi-AgE{b62(60)}",
    "npm": f"npm_{b62(36)}",
    "encoded": f"Bearer%20ghp_{b62(36)}",
}
_DELIMITERS = ("", "&a=1", "/x", "?a", "#f", ")")


@pytest.mark.parametrize("prefix", list(TOKENS), ids=list(TOKENS))
def test_a_token_shape_in_a_url_value_is_found_and_masked(prefix: str) -> None:
    """A token of its shortest real shape is found in a URL value (a path
    segment, a query value, right after a percent-encoded character) and
    shown as its prefix; a near miss or one inside a longer word is none,
    and so is any token in prose, which the masker still hides."""
    body, near = TOKENS[prefix]
    token = prefix + body
    for url in (f"https://h/{token}/x", f"https://h/x?q=Bearer%20{token}"):
        found = find_url_credentials(url)
        assert [(f.kind, f.shown) for f in found] == [("token", f"{prefix}***")]
        assert body not in masked_given_path(url)
    assert not find_url_credentials(f"https://h/{prefix}{near}/x")
    assert not find_url_credentials(f"https://h/x{token}/x")
    assert not find_url_credentials(f"set {token} now")
    assert body not in masked_given_path(f"set {token} now")


@pytest.mark.parametrize("prefix", list(TOKENS), ids=list(TOKENS))
def test_no_character_of_a_token_survives_the_masker(prefix: str) -> None:
    """A token is masked whole, a body that runs on past its shortest length
    too, whatever delimiter follows it, so a refusal message shows nothing
    of it but its prefix."""
    body = TOKENS[prefix][0] + ("Zq9-" * 40 if prefix in _OPEN else "")
    if prefix in ("xapp-",):
        body = TOKENS[prefix][0] + "zq9" * 40
    for after in _DELIMITERS:
        text = f"https://h/x?q={prefix}{body}{after}"
        assert masked_given_path(text) == f"https://h/x?q={prefix}***{after}"
        assert find_url_credentials(text)


@pytest.mark.parametrize(
    ("prefix", "length"),
    [("glpat-", 20), ("gldt-", 20), ("glrt-", 20), ("AIza", 35)],
    ids=["glpat", "gldt", "glrt", "aiza"],
)
@pytest.mark.parametrize("at", ["first", "middle", "last"])
def test_a_random_body_needs_a_digit_and_both_cases_anywhere(
    prefix: str, length: int, at: str
) -> None:
    """A GitLab token's 20 characters, a Google key's 35, hold a digit, an
    upper- and a lower-case letter, each at any place; without any one of
    them it is no token (a CamelCase or a SHOUTING slug)."""
    place = {"first": 0, "middle": length // 2, "last": length - 3}[at]
    for char, filler in (("7", "Xy"), ("Q", "x7"), ("q", "X7")):
        without = (filler * length)[:length]
        body = without[:place] + char + without[place + 1 :]
        assert find_url_credentials(f"https://h/{prefix}{body}")
        assert not find_url_credentials(f"https://h/{prefix}{without}")


@pytest.mark.parametrize(
    "token",
    [
        *(f"ghp_{b62(37)}", f"npm_{b62(37)}", "AKIAT2KENABCDEFGHIJKL"),
        *(f"hf_{'Tq' * 17}x", f"hf_{'Tq' * 16}T1"),
        f"github_pat_{b62(22)}_{b62(60)}",
        *(f"AIza{b62(36)}", f"sk-ant-api03-{b62(93)}AAx"),
        f"sk-proj-{b62(59)}T3BlbkFJ{b62(58)}",
    ],
    ids=[
        *("ghp-37", "npm-37", "akia-17", "hf-35", "hf-digit"),
        *("pat-60", "aiza-36", "anthropic-96", "openai-59"),
    ],
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
        *("api_org_settings_page", "ASIAPACIFICREGION123", "sk-" + "a1" * 24),
        *("glpat-" + "a1" * 10, "AKIAIOSFODNN8EXAMPLE"),
        *("sk-ant-api03-key-rotation", "sk-proj-settings", "AIza-config"),
        *("sk-" + "0f" * 32, "0f" * 32),
        *("xoxr-Configuration", "xoxa-ABCDEFGHrelease"),
        *("xoxa-123e4567-e89b-12d3-a456-426614174000",),
        *("xapp-1-Overview-2024-update", "glptt-HowToRotatePipelineTrig"),
        *("gloas-ApplicationSecretRotation", "xoxb-12345678-ReleaseNotesForVersion2"),
        *("xapp-1-Overview-2024-updatenotes", "glcbt-ContinuousBuildTokenGuide"),
        *("glpat-ApiProjectPypiInstallSetupPypiBuild", "glpat-NPM_OVERVIEW_LEGACY74"),
        *("glrt-ServiceAnthropicAnthropicApi",),
        *("gldt-TOKEN_ACCESS_RELEASE_PYPI_NOTES_DOCS269",),
        *("AIzaGitlabInstallAppRefreshDeployGuides",),
    ],
    ids=[
        *("pat-slug", "glpat-slug", "xoxb-slug", "xapp-slug", "pypi-slug"),
        *("hf-call", "hf-env", "npm-config", "api-org-slug", "asia-word", "sk"),
        *("glpat-no-upper", "akia-not-base32", "anthropic-slug"),
        *("openai-slug", "google-slug", "sk-hash", "sha256"),
        *("xoxr-word", "xoxa-word", "xoxa-uuid", "xapp-words", "glptt-camel"),
        *("gloas-camel", "xoxb-legacy-words", "xapp-long-words", "glcbt-camel"),
        *("glpat-camel", "glpat-shouting", "glrt-camel", "gldt-shouting"),
        *("aiza-camel",),
    ],
)
def test_a_slug_in_a_url_is_no_token(text: str) -> None:
    """A slug, an environment variable, a documentation word in a token's
    loose legacy shape, a GitLab body with no upper-case letter or an AWS
    key id outside base32 is no token, in a URL's path or in a message;
    AWS's documented example key is one."""
    assert not find_url_credentials(f"https://docs.example/{text}")
    assert masked_given_path(text) == text
    assert find_url_credentials("https://h/AKIAIOSFODNN7EXAMPLE")


@pytest.mark.parametrize("half", [58, 74], ids=["58", "74"])
def test_an_openai_key_has_either_half_length(half: int) -> None:
    """Each half of an OpenAI project key is 58 or 74 characters, as the
    gitleaks rule states."""
    body = f"{b62(half)}T3BlbkFJ{b62(half)}"
    assert find_url_credentials(f"https://h/sk-proj-{body}")
    assert masked_given_path(f"sk-proj-{body}") == "sk-proj-***"


@pytest.mark.parametrize("token", list(_EARLIER.values()), ids=list(_EARLIER))
def test_a_token_found_before_the_gitleaks_shapes_is_found_still(
    token: str,
) -> None:
    """No shape is narrower than the one before it: each token row of the
    earlier corpus is found and masked whole. (Its AWS rows, a key id
    outside base32, are none now on purpose, as ``akia-not-base32``.)"""
    url = f"{_IN_URL}{token}"
    assert find_url_credentials(url)
    assert masked_given_path(url).endswith("***")


@pytest.mark.parametrize(
    "token",
    [
        "pypi-AgENdGVzdC5weXBpLm9yZw" + b62(60),
        "pypi-AgEIcHlwaS5vcmc" + b62(60),
        "xoxs-1234567890-1234567890-1234567890-abcdef12",
        "xoxo-1-2-3-0f",
        "xoxb-1234567890-1234567890",
        "xoxp-" + "-".join(["1234567890"] * 3) + "-" + b62(28),
        "xoxe-1-" + b62(146),
        "xoxe.xoxp-1-" + b62(166),
        "xapp-1-A0123ABCDEF-1234567890123-" + "0f" * 32,
        "glcbt-1_" + b62(20),
        "glptt-" + b62(20),
        "gloas-" + b62(64),
    ],
    ids=[
        *("testpypi", "pypi", "slack-legacy-s", "slack-legacy-o"),
        *("slack-bot", "slack-user", "slack-refresh", "slack-config", "xapp"),
        *("glcbt-gitleaks", "glptt-earlier", "gloas-gitleaks"),
    ],
)
def test_each_stated_shape_is_found_and_masked_whole(token: str) -> None:
    """Each shape the module states: a TestPyPI token as well as a PyPI
    one, each gitleaks Slack shape read, and both a GitLab shape and the
    earlier one."""
    assert find_url_credentials(f"{_IN_URL}{token}")
    prefix = token.split("-", 1)[0] + "-"
    assert masked_given_path(f"{_IN_URL}{token}") == f"{_IN_URL}{prefix}***"
