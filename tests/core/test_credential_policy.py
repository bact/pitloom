# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The credential fingerprint, :class:`CredentialPolicy`, the
``accept-url-credentials`` and ``url-credentials`` keys and the cascade
that unites them with the flags.

See also: :mod:`tests.cli.test_cli_credential_flags` (the flags).
"""

from __future__ import annotations

import dataclasses
import hashlib
import logging
from collections.abc import Callable
from typing import Any

import pytest

from pitloom.core.config import PitloomConfig, parse_pitloom_config
from pitloom.core.config_cascade import ConfigOverrides, apply_overrides
from pitloom.core.credential_policy import (
    FINGERPRINT_RE,
    CredentialPolicy,
    fingerprint,
    full_fingerprint,
    read_accept_key,
    read_mode_key,
    require_fingerprint,
)
from pitloom.core.internal_error import InternalError
from pitloom.messages import code_of
from pitloom.messages._fields import FIELDS

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


def test_refuse_is_not_an_accepted_value_and_off_by_default() -> None:
    assert not CredentialPolicy().refuse
    policy = CredentialPolicy(refuse=True)
    assert not policy.accepts_value(_VALUE)
    assert policy.refuse


def test_policy_takes_any_iterable_but_not_a_string() -> None:
    listed: Any = [_OTHER]
    assert CredentialPolicy(accepted=listed).accepted == {_OTHER}
    single: Any = _OTHER
    with pytest.raises(ValueError, match="not a fingerprint"):
        CredentialPolicy(accepted=single)


def test_an_entry_in_both_sets_survives_replacing_accepted() -> None:
    """Both sets keep it, so a policy rebuilt without *accepted* still
    accepts it through *inherited*."""
    both = CredentialPolicy(accepted=frozenset({_FULL}), inherited=frozenset({_FULL}))
    rebuilt = dataclasses.replace(both, accepted=frozenset())
    assert rebuilt.inherited == {_FULL} and rebuilt.accepts_value(_VALUE)


def test_union_keeps_both_sides() -> None:
    one = CredentialPolicy(accepted=frozenset({_OTHER}))
    two = CredentialPolicy(accepted=frozenset({_FULL[:23]}), refuse=True)
    united = one.union(two)
    assert united.accepted == {_OTHER, _FULL[:23]}
    assert united.refuse
    assert not one.union(CredentialPolicy()).refuse


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


@pytest.mark.parametrize(
    ("table", "mode", "refuse"),
    [
        pytest.param({}, "warn", False, id="absent"),
        pytest.param({"url-credentials": "warn"}, "warn", False, id="warn"),
        pytest.param({"url-credentials": "refuse"}, "refuse", True, id="refuse"),
    ],
)
def test_read_mode_key(table: dict[str, Any], mode: str, refuse: bool) -> None:
    assert read_mode_key(table) == mode
    cfg = _parse(table)
    assert cfg.url_credentials == mode and cfg.credential_policy.refuse is refuse


@pytest.mark.parametrize(
    "value",
    ["ghp_secretvalue", "Refuse", "", True, 1, ["refuse"]],
    ids=["secret", "case", "empty", "bool", "int", "array"],
)
@pytest.mark.parametrize("is_setup_cfg", [False, True], ids=["pyproject", "setup-cfg"])
def test_read_mode_key_refuses_without_quoting(value: Any, is_setup_cfg: bool) -> None:
    table = "[tool:pitloom]" if is_setup_cfg else "[tool.pitloom]"
    with pytest.raises(ValueError) as info:
        parse_pitloom_config(
            {"tool": {"pitloom": {"url-credentials": value}}},
            is_setup_cfg=is_setup_cfg,
        )
    assert str(info.value) == f'{table} url-credentials: must be "warn" or "refuse"'
    assert code_of(info.value) == "option-invalid"


def test_a_bad_mode_in_a_built_config_raises_when_built() -> None:
    with pytest.raises(ValueError, match="url_credentials: must be") as info:
        PitloomConfig(url_credentials="S3CRET")
    assert "S3CRET" not in str(info.value)
    assert code_of(info.value) == "option-invalid"


@pytest.mark.parametrize(
    "table",
    [{"accept-url-credentials": [_OTHER]}, {"url-credentials": "refuse"}],
    ids=["accept", "mode"],
)
def test_the_credential_keys_are_silent(
    table: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING):
        _parse(table, source="/p/pyproject.toml")
    assert not caplog.records


def test_the_removed_allow_key_is_an_unknown_key(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``allow-url-credentials`` is gone: like any key Pitloom does not
    know, it warns and is ignored."""
    with caplog.at_level(logging.WARNING):
        cfg = _parse({"allow-url-credentials": True}, source="/p/pyproject.toml")
    assert not cfg.credential_policy.refuse
    (line,) = caplog.messages
    assert "unknown key 'allow-url-credentials'" in line


@pytest.mark.parametrize(
    ("config", "flags", "accepted", "refuse"),
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
            CredentialPolicy(accepted=frozenset({_FULL[:23]}), refuse=True),
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
    refuse: bool,
) -> None:
    cfg = apply_overrides(
        PitloomConfig(accept_url_credentials=config),
        ConfigOverrides(credentials=flags),
    )
    assert cfg.accept_url_credentials == accepted
    assert cfg.url_credentials == ("refuse" if refuse else "warn")
    assert cfg.credential_policy == CredentialPolicy(
        accepted=frozenset(accepted), refuse=refuse
    )


@pytest.mark.parametrize(
    "flags", [None, CredentialPolicy()], ids=["no-flags", "flags-without-refuse"]
)
def test_the_config_refuse_mode_survives_flags_without_it(
    flags: CredentialPolicy | None,
) -> None:
    """CLI > pyproject > default: a store-true flag turns refusal on, and
    its absence never turns the project's refusal off."""
    cfg = apply_overrides(
        PitloomConfig(url_credentials="refuse"), ConfigOverrides(credentials=flags)
    )
    assert cfg.url_credentials == "refuse" and cfg.credential_policy.refuse


@pytest.mark.parametrize(
    "build",
    [
        lambda: PitloomConfig(accept_url_credentials=("nope",)),
        lambda: dataclasses.replace(PitloomConfig(), accept_url_credentials=("x",)),
    ],
    ids=["constructed", "replaced"],
)
def test_a_bad_fingerprint_in_a_built_config_raises_when_built(
    build: Callable[[], PitloomConfig],
) -> None:
    with pytest.raises(ValueError, match="not a fingerprint"):
        build()


def test_the_fingerprint_pattern_is_the_message_fields() -> None:
    """One spelling: the policy compiles the message field's pattern."""
    assert FINGERPRINT_RE.pattern == FIELDS["fingerprint"].pattern


@pytest.mark.parametrize(
    "value", [1, 0, "refuse", "yes", None], ids=["one", "zero", "refuse", "yes", "none"]
)
def test_refuse_takes_only_a_bool(value: Any) -> None:
    """A truthy non-bool is no silent ``warn``: it is refused."""
    with pytest.raises(ValueError) as info:
        CredentialPolicy(refuse=value)
    assert str(info.value) == "CredentialPolicy refuse: must be True or False"
    assert code_of(info.value) == "option-invalid"


@pytest.mark.parametrize("value", [True, "Refuse", 1, None], ids=str)
def test_a_built_config_takes_only_a_mode_string(value: Any) -> None:
    with pytest.raises(ValueError, match="url_credentials: must be"):
        PitloomConfig(url_credentials=value)
