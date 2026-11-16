# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The credential fingerprint, :class:`CredentialPolicy`, the
``accept-url-credentials`` key and the cascade that unites it with the flags.

See also: :mod:`tests.cli.test_cli_credential_flags` (the flags).
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

import pytest

from pitloom.core.config import PitloomConfig, parse_pitloom_config
from pitloom.core.config_cascade import ConfigOverrides, apply_overrides
from pitloom.core.credential_policy import (
    CredentialPolicy,
    fingerprint,
    full_fingerprint,
    read_accept_key,
    require_fingerprint,
)
from pitloom.core.internal_error import InternalError
from pitloom.messages import code_of

_VALUE = "https://user:hunter2@example.com/pkg.tar.gz"
_FULL = "sha256:" + hashlib.sha256(_VALUE.encode()).hexdigest()
_OTHER = "sha256:" + "0" * 16


def _parse(pitloom: dict[str, Any], source: str | None = None) -> PitloomConfig:
    return parse_pitloom_config({"tool": {"pitloom": pitloom}}, source=source)


def test_fingerprint_is_the_sha256_of_the_whole_value() -> None:
    # The SHA-256 of the empty string, a published test vector.
    assert fingerprint("") == "sha256:e3b0c44298fc1c14"
    assert full_fingerprint("") == (
        "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )
    assert fingerprint(_VALUE) == _FULL[:23]
    assert full_fingerprint(_VALUE) == _FULL


def test_fingerprint_of_a_lone_surrogate_does_not_raise() -> None:
    assert fingerprint("\ud800").startswith("sha256:")


@pytest.mark.parametrize(
    ("text", "valid"),
    [
        pytest.param("sha256:" + "a" * 15, False, id="15-hex"),
        pytest.param("sha256:" + "a" * 16, True, id="16-hex"),
        pytest.param("sha256:" + "a" * 64, True, id="64-hex"),
        pytest.param("sha256:" + "a" * 65, False, id="65-hex"),
        pytest.param("sha256:" + "A" * 16, False, id="uppercase"),
        pytest.param("SHA256:" + "a" * 16, False, id="uppercase-prefix"),
        pytest.param("a" * 16, False, id="no-prefix"),
        pytest.param("sha256:" + "g" * 16, False, id="not-hex"),
        pytest.param("sha256:" + "a" * 16 + "\n", False, id="trailing-newline"),
    ],
)
def test_require_fingerprint(text: str, valid: bool) -> None:
    if valid:
        assert require_fingerprint(text) == text
    else:
        with pytest.raises(ValueError, match="not a fingerprint") as info:
            require_fingerprint(text)
        assert text not in str(info.value)
        assert code_of(info.value) == "option-invalid"


@pytest.mark.parametrize(
    ("entry", "accepted"),
    [
        pytest.param(_FULL[:23], True, id="printed-16"),
        pytest.param(_FULL[:30], True, id="longer-prefix"),
        pytest.param(_FULL, True, id="full"),
        # Right length, not a prefix of the digest: only the prefix fails.
        pytest.param(_OTHER, False, id="not-a-prefix"),
    ],
)
def test_accepts_value_matches_a_prefix_of_the_full_digest(
    entry: str, accepted: bool
) -> None:
    policy = CredentialPolicy(accepted=frozenset({entry}))
    assert policy.accepts_value(_VALUE) is accepted
    assert policy.accepts(_FULL) is accepted


def test_a_prefix_shorter_than_16_is_refused_though_it_matches() -> None:
    """A prefix of the digest, but 15 digits: only the length fails."""
    assert _FULL.startswith(_FULL[:22])
    with pytest.raises(ValueError, match="not a fingerprint"):
        CredentialPolicy(accepted=frozenset({_FULL[:22]}))


def test_a_longer_entry_does_not_accept_the_printed_fingerprint() -> None:
    """Digits past the printed 16 cannot be checked against it: no match."""
    policy = CredentialPolicy(accepted=frozenset({_FULL[:30]}))
    assert not policy.accepts(fingerprint(_VALUE))
    assert CredentialPolicy(accepted=frozenset({_FULL[:23]})).accepts(
        fingerprint(_VALUE)
    )


def test_accepts_refuses_what_is_not_a_fingerprint() -> None:
    policy = CredentialPolicy(accepted=frozenset({_FULL[:23]}))
    with pytest.raises(InternalError):
        policy.accepts(_FULL + "00")


def test_allow_all_is_not_an_accepted_value() -> None:
    policy = CredentialPolicy(allow_all=True)
    assert not policy.accepts_value(_VALUE)
    assert policy.allow_all


def test_policy_takes_any_iterable_but_not_a_string() -> None:
    listed: Any = [_OTHER]
    assert CredentialPolicy(accepted=listed).accepted == {_OTHER}
    single: Any = _OTHER
    with pytest.raises(ValueError, match="not a fingerprint"):
        CredentialPolicy(accepted=single)


def test_union_keeps_both_sides() -> None:
    one = CredentialPolicy(accepted=frozenset({_OTHER}))
    two = CredentialPolicy(accepted=frozenset({_FULL[:23]}), allow_all=True)
    united = one.union(two)
    assert united.accepted == {_OTHER, _FULL[:23]}
    assert united.allow_all
    assert not one.union(CredentialPolicy()).allow_all


@pytest.mark.parametrize(
    ("table", "expected"),
    [
        pytest.param({}, (), id="absent"),
        pytest.param({"accept-url-credentials": []}, (), id="empty"),
        pytest.param(
            {"accept-url-credentials": [_FULL[:23], _OTHER, _OTHER]},
            (_OTHER, _FULL[:23]),
            id="sorted-once",
        ),
    ],
)
def test_read_accept_key(table: dict[str, Any], expected: tuple[str, ...]) -> None:
    assert read_accept_key(table) == expected
    assert _parse(table).accept_url_credentials == expected


@pytest.mark.parametrize(
    ("value", "match"),
    [
        pytest.param("ghp_secretvalue", "credentials: must be an array", id="string"),
        pytest.param({"a": 1}, "credentials: must be an array", id="table"),
        pytest.param(["ghp_secretvalue"], "credentials entry 0: not a", id="bad-entry"),
        pytest.param([_OTHER, 7], "credentials entry 1: not a", id="wrong-type-entry"),
    ],
)
def test_read_accept_key_refuses_without_quoting(value: Any, match: str) -> None:
    with pytest.raises(ValueError, match=match) as info:
        _parse({"accept-url-credentials": value})
    assert "ghp_secretvalue" not in str(info.value)
    assert str(info.value).startswith("[tool.pitloom] accept-url-credentials")
    assert code_of(info.value) == "option-invalid"


def test_allow_key_in_pyproject_warns_and_never_allows_all(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        cfg = _parse({"allow-url-credentials": True}, source="/p/pyproject.toml")
    assert cfg.allow_url_credentials is False
    assert not cfg.credential_policy.allow_all
    (line,) = [r.getMessage() for r in caplog.records]
    assert line == ("allow-url-credentials: CLI only; ignored in [tool.pitloom]")
    assert "unknown key" not in line


def test_allow_key_warns_once_per_process(caplog: pytest.LogCaptureFixture) -> None:
    """Any value of the key, from any file: said once per key and table."""
    with caplog.at_level(logging.WARNING):
        for source in ("/a/pyproject.toml", "/a/pyproject.toml", "/b/pyproject.toml"):
            _parse({"allow-url-credentials": False}, source=source)
    warned = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warned) == 1


def test_accept_key_is_silent(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        _parse({"accept-url-credentials": [_OTHER]})
    assert not caplog.records


@pytest.mark.parametrize(
    ("config", "flags", "accepted", "allow_all"),
    [
        pytest.param((), None, (), False, id="neither"),
        pytest.param((_OTHER,), None, (_OTHER,), False, id="config-only"),
        pytest.param(
            (),
            CredentialPolicy(accepted=frozenset({_FULL[:23]})),
            (_FULL[:23],),
            False,
            id="flag-only",
        ),
        pytest.param(
            (_OTHER,),
            CredentialPolicy(accepted=frozenset({_FULL[:23]}), allow_all=True),
            (_OTHER, _FULL[:23]),
            True,
            id="union",
        ),
        pytest.param(
            (_OTHER,), CredentialPolicy(), (_OTHER,), False, id="empty-flag-keeps"
        ),
    ],
)
def test_apply_overrides_unites_the_flags_with_the_config(
    config: tuple[str, ...],
    flags: CredentialPolicy | None,
    accepted: tuple[str, ...],
    allow_all: bool,
) -> None:
    cfg = apply_overrides(
        PitloomConfig(accept_url_credentials=config),
        ConfigOverrides(credentials=flags),
    )
    assert cfg.accept_url_credentials == accepted
    assert cfg.allow_url_credentials is allow_all
    assert cfg.credential_policy == CredentialPolicy(
        accepted=frozenset(accepted), allow_all=allow_all
    )


def test_config_allow_all_survives_an_override_without_it() -> None:
    """A library caller's ``allow_url_credentials`` is ORed, never reset."""
    cfg = apply_overrides(
        PitloomConfig(allow_url_credentials=True),
        ConfigOverrides(credentials=CredentialPolicy()),
    )
    assert cfg.allow_url_credentials


def test_a_bad_fingerprint_in_a_built_config_raises() -> None:
    with pytest.raises(ValueError, match="not a fingerprint"):
        _ = PitloomConfig(accept_url_credentials=("nope",)).credential_policy
