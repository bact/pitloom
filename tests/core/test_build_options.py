# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for :class:`pitloom.core.build_options.BuildOptions`:
validation (the one validation point for every library surface),
``given``/``settings()``, and the three warning methods
(``warn_no_effect``, ``settle``, ``settle_not_applicable``).

See also: :mod:`tests.test_build_flag_warnings` for the cross-surface
matrix (CLI, library API, every target kind) asserting each ignored flag
is reported exactly once.
"""

from __future__ import annotations

import dataclasses
import inspect
import logging
from typing import Any

import pytest

from pitloom.assemble import generate, generate_project_sbom
from pitloom.core._models_wheel_types import BuildSettings
from pitloom.core.build_options import SDIST_TARGET_REASON, BuildOptions
from pitloom.core.models import get_wheel_files
from pitloom.embed import ConfigOverrides


def _build_warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if record.levelno == logging.WARNING and "has no effect" in record.getMessage()
    ]


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"timeout": 0}, ValueError),
        ({"timeout": -1}, ValueError),
        ({"timeout": 604_801}, ValueError),
        ({"timeout": True}, TypeError),
        ({"timeout": 1.5}, TypeError),
        ({"timeout": "900"}, TypeError),
        ({"allow": "false"}, TypeError),
        ({"allow": 1}, TypeError),
        ({"no_isolation": "yes"}, TypeError),
        ({"no_isolation": None}, TypeError),
    ],
    ids=str,
)
def test_invalid_value_raises_at_construction(
    kwargs: dict[str, Any], error: type[Exception]
) -> None:
    """Construction is the one validation point: every library surface
    takes a ``BuildOptions``, so an invalid value can never reach one. A
    truthy non-bool ``allow`` (e.g. ``"false"``) must never enable code
    execution."""
    with pytest.raises(error):
        BuildOptions(**kwargs)


def test_replace_revalidates() -> None:
    with pytest.raises(ValueError):
        dataclasses.replace(BuildOptions(timeout=30), timeout=0)


@pytest.mark.parametrize("timeout", [1, 900, 604_800])
def test_valid_timeout_accepted(timeout: int) -> None:
    assert BuildOptions(timeout=timeout).timeout == timeout


def test_is_frozen() -> None:
    options = BuildOptions()
    with pytest.raises(dataclasses.FrozenInstanceError):
        options.allow = True  # type: ignore[misc]


@pytest.mark.parametrize(
    ("options", "expected"),
    [
        (BuildOptions(), ()),
        (BuildOptions(allow=True), ("--allow-build",)),
        (
            BuildOptions(timeout=5, no_isolation=True),
            ("--no-build-isolation", "--build-timeout"),
        ),
        (
            BuildOptions(allow=True, no_isolation=True, timeout=5),
            ("--allow-build", "--no-build-isolation", "--build-timeout"),
        ),
    ],
    ids=["none", "allow", "no-isolation+timeout", "all"],
)
def test_given_lists_flags_in_cli_order(
    options: BuildOptions, expected: tuple[str, ...]
) -> None:
    assert options.given == expected


@pytest.mark.parametrize(
    ("options", "expected"),
    [
        (BuildOptions(), None),
        (BuildOptions(no_isolation=True, timeout=5), None),
        (BuildOptions(allow=True), BuildSettings(isolated=True, timeout=1200)),
        (
            BuildOptions(allow=True, no_isolation=True, timeout=5),
            BuildSettings(isolated=False, timeout=5),
        ),
    ],
    ids=["none", "stray-only", "allow-default-timeout", "allow-all"],
)
def test_settings(options: BuildOptions, expected: BuildSettings | None) -> None:
    assert options.settings() == expected


def test_settle_warns_once_per_stray_flag_and_resets(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        settled = BuildOptions(no_isolation=True, timeout=5).settle("proj")

    assert _build_warnings(caplog) == [
        "Build: proj: --no-build-isolation has no effect without --allow-build",
        "Build: proj: --build-timeout has no effect without --allow-build",
    ]
    assert settled == BuildOptions()


def test_settle_returns_self_when_allow(caplog: pytest.LogCaptureFixture) -> None:
    """``allow`` set means nothing here is stray -- whether ``allow``
    itself has an effect depends on the target, checked elsewhere."""
    options = BuildOptions(allow=True, no_isolation=True, timeout=5)
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        settled = options.settle("proj")

    assert not _build_warnings(caplog)
    assert not caplog.records
    assert settled is options


def test_settle_is_idempotent(caplog: pytest.LogCaptureFixture) -> None:
    """Settling an already-settled (or always-default) value is a silent
    no-op -- what keeps a downstream re-settle (e.g. inside
    ``get_wheel_files()``) from warning a second time."""
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        once = BuildOptions(no_isolation=True, timeout=5).settle("proj")
        assert _build_warnings(caplog)  # the one legitimate warning, settled away
        caplog.clear()

        twice = once.settle("proj")
        default_settled = BuildOptions().settle("proj")

        assert not _build_warnings(caplog)
        assert not caplog.records
    assert twice == once == BuildOptions()
    assert default_settled == BuildOptions()


def test_settle_not_applicable_warns_every_given_flag_and_resets(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Unlike ``settle()``, ``allow`` is not exempt here: a target the
    caller already knows won't reach file discovery makes every given
    flag ineffective, ``--allow-build`` included."""
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        settled = BuildOptions(allow=True, timeout=5).settle_not_applicable(
            "demo.tar.gz", "for an sdist archive target"
        )

    assert _build_warnings(caplog) == [
        "Build: demo.tar.gz: --allow-build has no effect for an sdist archive target",
        "Build: demo.tar.gz: --build-timeout has no effect for an sdist archive target",
    ]
    assert settled == BuildOptions()


def test_settle_not_applicable_is_idempotent(caplog: pytest.LogCaptureFixture) -> None:
    """Settling an already-settled (or always-default) value is a silent
    no-op -- what keeps a downstream re-settle (e.g. a CLI handler
    settling before a metadata read, then ``generate_project_sbom()``
    settling again for the same target) from warning a second time."""
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        once = BuildOptions(timeout=5).settle_not_applicable(
            "demo.tar.gz", "for an sdist archive target"
        )
        assert _build_warnings(caplog)  # the one legitimate warning, settled away
        caplog.clear()

        twice = once.settle_not_applicable("demo.tar.gz", "for an sdist archive target")
        default_settled = BuildOptions().settle_not_applicable(
            "demo.tar.gz", "for an sdist archive target"
        )

        assert not _build_warnings(caplog)
        assert not caplog.records
    assert twice == once == BuildOptions()
    assert default_settled == BuildOptions()


def test_settle_not_applicable_nothing_given_warns_nothing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        settled = BuildOptions().settle_not_applicable(
            "demo.tar.gz", "for an sdist archive target"
        )

    assert not caplog.records
    assert settled == BuildOptions()


def test_warn_no_effect_one_line_per_flag(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        BuildOptions(allow=True, timeout=5).warn_no_effect("x.whl", "for this target")
        BuildOptions().warn_no_effect("y.whl", "for this target")

    assert _build_warnings(caplog) == [
        "Build: x.whl: --allow-build has no effect for this target",
        "Build: x.whl: --build-timeout has no effect for this target",
    ]


@pytest.mark.parametrize(
    "entry_point",
    [generate, generate_project_sbom, get_wheel_files, ConfigOverrides],
    ids=lambda f: f.__name__,
)
def test_every_surface_takes_one_build_options(entry_point: object) -> None:
    """Drift guard: every library surface takes the build flags as one
    ``build_options: BuildOptions`` parameter defaulting to "none given",
    never as separate per-flag parameters that would need their own
    validation and warning wiring."""
    params = inspect.signature(entry_point).parameters  # type: ignore[arg-type]
    assert not {"allow_build", "no_build_isolation", "build_timeout"} & set(params)
    param = params["build_options"]
    assert param.annotation in (BuildOptions, "BuildOptions")
    assert param.default == BuildOptions()


def test_sdist_target_reason_is_nonempty_and_names_no_build_and_read() -> None:
    """:data:`~pitloom.core.build_options.SDIST_TARGET_REASON` is the one
    reason string ``cli/commands/project.py``, ``cli/commands/generate.py``,
    and ``assemble/_generators.py`` all import and pass to
    ``settle_not_applicable()`` -- see
    :mod:`tests.test_build_flag_warnings`'s ``_SDIST`` cases (``cli-project``/
    ``cli-generate``/``lib-generate``/``lib-generate_project_sbom``), which
    already drift-guard the four surfaces against each other end to end."""
    assert SDIST_TARGET_REASON.startswith("for an sdist archive target")
