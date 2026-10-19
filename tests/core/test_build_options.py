# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for :class:`pitloom.core.build_options.BuildOptions`:
validation (the one validation point for every library surface),
``given``/``settings()``, and the settle methods (``settle``,
``settle_not_applicable``, ``settle_target``).

See also: :mod:`tests.test_build_flag_warnings` for the cross-surface
matrix (CLI, library API, every target kind) asserting each ignored flag
is reported exactly once.
"""

from __future__ import annotations

import dataclasses
import inspect
import logging
import os
import sys
from pathlib import Path
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


_STRAY = BuildOptions(no_isolation=True, timeout=5)
_ALLOWED = BuildOptions(allow=True, timeout=5)


@pytest.mark.parametrize("options", [_STRAY, _ALLOWED], ids=["stray", "allowed"])
def test_settle_target_sdist_file_warns_every_flag(
    caplog: pytest.LogCaptureFixture, tmp_path: Path, options: BuildOptions
) -> None:
    """A file is an sdist archive: every given flag, ``--allow-build``
    included, gets the sdist reason -- never "without --allow-build"."""
    sdist = tmp_path / "demo-1.0.tar.gz"
    sdist.write_bytes(b"")
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        settled = options.settle_target(sdist)

    lines = _build_warnings(caplog)
    assert len(lines) == len(options.given)
    assert all(line.endswith(SDIST_TARGET_REASON) for line in lines), lines
    assert settled == BuildOptions()


def test_settle_target_project_dir_settles_like_settle(
    caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    """A directory settles exactly as ``settle()`` does: stray flags warn
    "without --allow-build"; with ``allow`` nothing warns and the value
    (timeout included) is kept."""
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        stray = _STRAY.settle_target(tmp_path)
        allowed = _ALLOWED.settle_target(tmp_path)

    assert _build_warnings(caplog) == [
        f"Build: {tmp_path}: --no-build-isolation has no effect without --allow-build",
        f"Build: {tmp_path}: --build-timeout has no effect without --allow-build",
    ]
    assert stray == BuildOptions()
    assert allowed is _ALLOWED


@pytest.mark.parametrize("options", [_STRAY, _ALLOWED], ids=["stray", "allowed"])
def test_settle_target_missing_path_settles_nothing(
    caplog: pytest.LogCaptureFixture, tmp_path: Path, options: BuildOptions
) -> None:
    """A missing path warns nothing and keeps every flag: the caller's
    read fails it with an ERROR alone, and a stray flag is not silently
    dropped before that."""
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        settled = options.settle_target(tmp_path / "missing")

    assert not caplog.records
    assert settled is options


@pytest.mark.parametrize(
    ("name", "warns"),
    [
        ("demo-1.0.0.tar.gz", True),
        ("demo-1.0.0.ZIP", True),
        ("notes.txt", False),
        ("demo-1.0.0-py3-none-any.whl", False),
    ],
)
def test_settle_target_warns_for_an_sdist_archive_only(
    caplog: pytest.LogCaptureFixture, tmp_path: Path, name: str, warns: bool
) -> None:
    """Only a real sdist archive gets the sdist reason. Any other file is
    no project target either, so it settles nothing: a warning naming a
    target kind the path never had would contradict the ``ERROR:`` the
    caller's read prints right after it."""
    target = tmp_path / name
    target.write_text("x\n", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="pitloom"):
        settled = _STRAY.settle_target(target)

    assert bool(caplog.records) == warns
    assert (settled is _STRAY) != warns
    if warns:
        # Not just "warned", but warned with the sdist reason -- not a
        # plain settle() warning (e.g. "without --allow-build").
        lines = _build_warnings(caplog)
        assert lines
        assert all(line.endswith(SDIST_TARGET_REASON) for line in lines), lines


# One condition, not two decorators: a decorator's argument is evaluated
# at import time, so a bare os.geteuid() call would fail the whole module
# on Windows, where it does not exist, however it is skipped afterwards.
_POSIX_PERMISSION_BITS = sys.platform != "win32" and os.geteuid() != 0


@pytest.mark.skipif(
    not _POSIX_PERMISSION_BITS,
    reason="POSIX permission bits, and root ignores them",
)
def test_settle_target_unreadable_directory_does_not_raise(
    caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    """Below Python 3.14 ``Path.is_file()`` propagates ``PermissionError``
    for a path under an unsearchable directory;
    settling must not, on any version."""
    parent = tmp_path / "locked"
    parent.mkdir()
    target = parent / "demo-1.0.0.tar.gz"
    target.write_text("x\n", encoding="utf-8")
    parent.chmod(0o000)
    try:
        # Non-vacuity: the directory really is unsearchable here.
        with pytest.raises(PermissionError):
            target.read_bytes()
        if sys.version_info < (3, 14):
            # 3.14's pathlib swallows it; os.path never raised.
            with pytest.raises(PermissionError):
                target.is_file()
        with caplog.at_level(logging.WARNING, logger="pitloom"):
            assert _STRAY.settle_target(target) is _STRAY
        assert not caplog.records
    finally:
        parent.chmod(0o700)


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
    reason string every sdist-target surface reaches through
    ``BuildOptions.settle_target()`` -- see
    :mod:`tests.test_build_flag_warnings`'s ``_SDIST`` cases (``cli-project``/
    ``cli-generate``/``lib-generate``/``lib-generate_project_sbom``), which
    already drift-guard the four surfaces against each other end to end."""
    assert SDIST_TARGET_REASON.startswith("for an sdist archive target")
