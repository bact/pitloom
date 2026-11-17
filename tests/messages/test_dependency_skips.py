# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A skipped dependency or extra entry is said by its cause: the closed cause
table picks the code and the line, a cause's ``failure`` or ``source_kind``
is given exactly when its line names one, ``quiet`` says nothing, and the
extra-gate helpers say their own codes.

See also: tests/messages/test_dependency_name_ambiguous.py.
"""

from __future__ import annotations

import logging
from typing import Any, cast, get_args

import pytest
from packaging.requirements import InvalidRequirement

from pitloom.core.internal_error import InternalError
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import MESSAGES, trusted_message
from pitloom.messages.dependencies import (
    CAUSE_LINES,
    Cause,
    warn_extra_gate_ambiguous,
    warn_extra_gate_unusable,
    warn_required_not_pep508,
    warn_skipped_dependency,
    warn_skipped_extra_entry,
)

_LOG = logging.getLogger("pitloom.dependency_messages")
_FAILURE = InvalidRequirement("Expected end or semicolon")


def _printed(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        f"{r.levelname}: {r.getMessage()} [{getattr(r, CODE_ATTR)}]"
        for r in caplog.records
    ]


def test_the_cause_type_is_the_cause_table() -> None:
    assert set(get_args(Cause)) == set(CAUSE_LINES)


@pytest.mark.parametrize(
    ("cause", "extra", "code"),
    [
        ("not-pep-508", {}, "requirement-invalid"),
        ("not-convertible", {"failure": _FAILURE}, "requirement-invalid"),
        ("local-source", {"source_kind": "path"}, "requirement-unusable"),
        ("unlisted-optional", {}, "requirement-invalid"),
    ],
)
def test_a_dependency_cause_picks_its_code(
    cause: Cause, extra: dict[str, Any], code: str, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    warn_skipped_dependency(
        _LOG,
        cause,
        dependency="a @ x",
        declared_in="Poetry",
        **extra,
    )
    (line,) = _printed(caplog)
    assert line.startswith("WARNING: dependency 'a @ x' (Poetry): ")
    assert line.endswith(f"; skipped [{code}]")
    assert trusted_message(line) is MESSAGES[code]


@pytest.mark.parametrize(
    ("cause", "extra"),
    [
        ("not-pep-508", {}),
        ("marker", {"failure": _FAILURE}),
        ("undeclared-extra", {}),
        ("cycle", {}),
        ("undeclared-dependency", {}),
    ],
)
def test_an_extra_entry_cause_is_requirement_invalid(
    cause: Cause, extra: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    warn_skipped_extra_entry(
        _LOG,
        cause,
        extra="all",
        dependency="demo[dev]",
        declared_in="optional-dependencies",
        **extra,
    )
    (line,) = _printed(caplog)
    assert line.startswith(
        "WARNING: extra 'all' entry 'demo[dev]' (optional-dependencies): "
    )
    assert trusted_message(line) is MESSAGES["requirement-invalid"]


@pytest.mark.parametrize(
    ("cause", "of_extra"),
    [
        ("cycle", False),
        ("marker", False),
        ("undeclared-extra", False),
        ("undeclared-dependency", False),
        ("not-convertible", True),
        ("local-source", True),
        ("unlisted-optional", True),
        ("no-such-cause", False),
        ("no-such-cause", True),
    ],
)
def test_a_cause_that_does_not_apply_is_an_internal_error(
    cause: str, of_extra: bool
) -> None:
    with pytest.raises(InternalError, match="cause"):
        if of_extra:
            warn_skipped_extra_entry(
                _LOG, cast(Cause, cause), extra="e", dependency="d", declared_in="x"
            )
        else:
            warn_skipped_dependency(
                _LOG, cast(Cause, cause), dependency="d", declared_in="x"
            )


@pytest.mark.parametrize(
    ("cause", "extra"),
    [
        ("not-convertible", {}),
        ("not-pep-508", {"failure": _FAILURE}),
        ("local-source", {}),
        ("not-pep-508", {"source_kind": "path"}),
    ],
    ids=["failure-missing", "failure-extra", "kind-missing", "kind-extra"],
)
def test_a_cause_value_is_given_exactly_when_named(
    cause: Cause, extra: dict[str, Any]
) -> None:
    with pytest.raises(InternalError, match="wrong cause"):
        warn_skipped_dependency(
            _LOG,
            cause,
            dependency="d",
            declared_in="x",
            **extra,
        )


def test_quiet_says_nothing_but_still_checks(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    warn_skipped_dependency(
        _LOG, "not-pep-508", dependency="d", declared_in="x", quiet=True
    )
    warn_skipped_extra_entry(
        _LOG, "cycle", extra="e", dependency="d", declared_in="x", quiet=True
    )
    assert not caplog.records
    with pytest.raises(InternalError):
        warn_skipped_dependency(
            _LOG, "cycle", dependency="d", declared_in="x", quiet=True
        )


def test_a_url_credential_in_a_dependency_is_masked(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING)
    warn_skipped_dependency(
        _LOG,
        "not-pep-508",
        dependency="a @ https://user:pass@h.example/a.whl ;;",
        declared_in="dependencies",
    )
    (record,) = caplog.records
    assert "pass@" not in record.getMessage()
    assert "pass@" not in str(record.args)


def test_the_gate_helpers_say_their_codes(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING)
    warn_required_not_pep508(_LOG, "not a requirement")
    warn_extra_gate_unusable(
        _LOG, package="demo", dependency='demo[x]; extra != "y"', self_reference=True
    )
    warn_extra_gate_unusable(
        _LOG, package="a", dependency='a; extra != "y"', self_reference=False
    )
    warn_extra_gate_ambiguous(_LOG, dependency="b", extras=["y", "x"])
    lines = _printed(caplog)
    assert [getattr(trusted_message(line), "code", None) for line in lines] == [
        "requirement-invalid",
        "extra-gate-unusable",
        "extra-gate-unusable",
        "extra-gate-ambiguous",
    ]
    assert lines[0].endswith("; recorded as required [requirement-invalid]")
    assert "self-reference" in lines[1] and "self-reference" not in lines[2]
    assert "needs extras 'x', 'y' together" in lines[3]


_LONG = "x" * 3000
_SECRET = "https://user:pass@h.example/a.whl"


@pytest.mark.parametrize("of_extra", [False, True], ids=["dependency", "extra"])
def test_a_long_failure_is_cut_and_masked(
    of_extra: bool, caplog: pytest.LogCaptureFixture
) -> None:
    """A parser's message can repeat a 3,000-character version or marker:
    the line cuts it to 120 characters, the credentials masked first."""
    caplog.set_level(logging.WARNING)
    failure = ValueError(f"bad {_SECRET} {_LONG}")
    if of_extra:
        warn_skipped_extra_entry(
            _LOG, "marker", extra="e", dependency="d", declared_in="x", failure=failure
        )
    else:
        warn_skipped_dependency(
            _LOG,
            "not-convertible",
            dependency="d",
            declared_in="Poetry",
            failure=failure,
        )
    (line,) = _printed(caplog)
    (record,) = caplog.records
    assert len(line) < 300 and "x..." in line
    assert "pass@" not in line and "pass@" not in str(record.args)
    assert trusted_message(line) is MESSAGES["requirement-invalid"]


def test_a_short_os_failure_keeps_its_description(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING)
    warn_skipped_dependency(
        _LOG,
        "not-convertible",
        dependency="d",
        declared_in="Poetry",
        failure=PermissionError(13, "Permission denied", "/abs/" + _LONG),
    )
    (line,) = _printed(caplog)
    assert "Permission denied" in line and _LONG not in line


@pytest.mark.parametrize(
    ("failure", "shown"),
    [
        (ValueError("y" * 120), "y" * 120),
        (ValueError("y" * 121), "y" * 120 + "..."),
        (OSError("y" * 121), "y" * 120 + "..."),
        (ValueError("a" + " " * 200 + "b"), "a b"),
    ],
    ids=["120-kept", "121-cut", "os-error-without-strerror-cut", "whitespace-run"],
)
def test_a_failure_is_cut_after_120_characters_on_one_line(
    failure: BaseException, shown: str, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    warn_skipped_dependency(
        _LOG, "not-convertible", dependency="d", declared_in="Poetry", failure=failure
    )
    (line,) = _printed(caplog)
    assert f"not convertible to PEP 508: {shown}; skipped" in line


def test_an_os_failure_shows_its_description_not_its_path(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING)
    warn_skipped_dependency(
        _LOG,
        "not-convertible",
        dependency="d",
        declared_in="Poetry",
        failure=PermissionError(13, "Permission denied", "/abs/" + "y" * 3000),
    )
    (line,) = _printed(caplog)
    assert "PEP 508: Permission denied; skipped" in line
    assert "/abs/" not in line and "Errno" not in line


def test_a_credential_across_the_cut_is_masked_before_it(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING)
    text = "x" * 100 + " https://user:secretpassword@h.example/a.whl" + " y" * 100
    warn_skipped_dependency(
        _LOG,
        "not-convertible",
        dependency="d",
        declared_in="Poetry",
        failure=ValueError(text),
    )
    (line,) = _printed(caplog)
    (record,) = caplog.records
    assert "https://***" in line
    assert "secret" not in line and "secret" not in str(record.args)
