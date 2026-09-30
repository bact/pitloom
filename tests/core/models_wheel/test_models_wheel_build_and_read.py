# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the generic, backend-agnostic build-and-read file discovery
mechanism (:mod:`pitloom.core._models_wheel_build_and_read`).

See also: tests/core/models_wheel/test_models_wheel_build_and_read_cleanup.py
(temp-dir cleanup on failure, timeout, Ctrl-C and termination signals),
tests/core/models_wheel/test_models_wheel_dispatch.py for the
facade-level dispatch tests that exercise this mechanism through
``get_wheel_files()``/``--allow-build``, and
tests/core/models_wheel/test_models_wheel_build_subprocess.py for the
child-process-tree mechanism this module delegates to.
"""

import logging
import zipfile
from pathlib import Path

import pytest

from pitloom.core._models_wheel_build_and_read import build_and_read_wheel
from pitloom.core._models_wheel_types import is_dist_info_path
from pitloom.core.build_signals import TerminationGuard
from pitloom.core.wheel_member_names import WheelFileMember
from tests.build_and_read_shared import (
    RUN_BUILD,
    FakeBuildState,
    install_fake_build,
    use_sys_tmp,
)


@pytest.fixture(name="fake_build")
def fixture_fake_build(monkeypatch: pytest.MonkeyPatch) -> FakeBuildState:
    return install_fake_build(monkeypatch)


@pytest.fixture(name="sys_tmp")
def fixture_sys_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return use_sys_tmp(tmp_path, monkeypatch)


def test_build_and_read_wheel_extracts_real_non_dist_info_files(
    fake_build: FakeBuildState, tmp_path: Path
) -> None:
    """A successful build's non-``.dist-info`` entries come back as
    ``IncludedFile`` pairs pointing at real, readable, on-disk files."""
    fake_build.entries = {
        "pkg/__init__.py": b"",
        "pkg/sub/mod.py": b"x = 1\n",
    }

    result = build_and_read_wheel(tmp_path, timeout=60)

    assert result is not None
    files, cleanup = result
    distribution_paths = {f.distribution_path for f in files}
    assert distribution_paths == {"pkg/__init__.py", "pkg/sub/mod.py"}
    for included_file in files:
        assert Path(included_file.path).is_file()
        assert not is_dist_info_path(included_file.distribution_path)
    cleanup()


@pytest.mark.usefixtures("fake_build")
def test_build_and_read_wheel_excludes_dist_info(tmp_path: Path) -> None:
    """``.dist-info/*`` entries -- genuinely present in the real,
    already-built wheel -- must never appear in the returned file list:
    every other backend's ``IncludedFile`` list is pre-build source
    files only."""
    result = build_and_read_wheel(tmp_path, timeout=60)

    assert result is not None
    files, cleanup = result
    assert not any(is_dist_info_path(f.distribution_path) for f in files)
    cleanup()


@pytest.mark.usefixtures("fake_build")
def test_build_and_read_wheel_cleanup_removes_temp_dir(tmp_path: Path) -> None:
    """The returned cleanup callback must actually delete the extraction
    temp directory -- callers rely on this to avoid leaking a temp dir
    per invocation."""
    result = build_and_read_wheel(tmp_path, timeout=60)

    assert result is not None
    files, cleanup = result
    extract_dir = Path(files[0].path).parent
    assert extract_dir.exists()

    cleanup()

    assert not extract_dir.exists()


def test_build_and_read_wheel_returns_none_on_build_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A build failure (network unavailable, backend not installable,
    the build script itself raising) must degrade to ``None`` plus a
    ``WARNING:``, never propagate -- same "None means fall back"
    contract as every static discoverer."""

    def _raise(
        project_dir: Path,
        work_dir: Path,
        *,
        isolated: bool,
        timeout: int,
        termination: TerminationGuard,
    ) -> Path:
        raise RuntimeError("simulated build backend failure")

    monkeypatch.setattr(RUN_BUILD, _raise)

    with caplog.at_level(logging.WARNING):
        result = build_and_read_wheel(tmp_path, timeout=60)

    assert result is None
    assert "build-and-read discovery failed" in caplog.text


def test_build_and_read_wheel_returns_none_on_zero_non_dist_info_files(
    fake_build: FakeBuildState, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A build that produces only ``.dist-info/*`` (zero real files) must
    be treated as a discovery failure, not an authoritative empty
    result -- per CLAUDE.md's None-vs-empty rule, this is a build
    failure, not a legitimately-empty wheel."""
    fake_build.entries = {}

    with caplog.at_level(logging.WARNING):
        result = build_and_read_wheel(tmp_path, timeout=60)

    assert result is None
    assert "no non-.dist-info files" in caplog.text


def test_build_and_read_wheel_isolated_true_by_default(
    fake_build: FakeBuildState, tmp_path: Path
) -> None:
    """``isolated`` defaults to ``True`` and is forwarded unchanged to
    the actual build invocation."""
    result = build_and_read_wheel(tmp_path, timeout=60)

    assert result is not None
    _, cleanup = result
    assert fake_build.isolated_seen == [True]
    cleanup()


def test_build_and_read_wheel_isolated_false_forwarded(
    fake_build: FakeBuildState, tmp_path: Path
) -> None:
    """``isolated=False`` (from ``--no-build-isolation``) is forwarded
    unchanged, never silently coerced back to ``True``."""
    result = build_and_read_wheel(tmp_path, isolated=False, timeout=60)

    assert result is not None
    _, cleanup = result
    assert fake_build.isolated_seen == [False]
    cleanup()


def test_build_and_read_wheel_forwards_timeout_unchanged(
    fake_build: FakeBuildState, tmp_path: Path
) -> None:
    """*timeout* is a required keyword with no default here -- it must
    reach the build subprocess unchanged, never substituted with some
    other default."""
    result = build_and_read_wheel(tmp_path, timeout=777)

    assert result is not None
    _, cleanup = result
    assert fake_build.timeout_seen == [777]
    cleanup()


def test_extract_wheel_to_included_files_skips_directory_entries(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An explicit ZIP directory entry (``info.is_dir()``) must never
    produce an ``IncludedFile`` -- only real file entries do."""

    def _fake_run_with_dir_entry(
        project_dir: Path,
        work_dir: Path,
        *,
        isolated: bool,
        timeout: int,
        termination: TerminationGuard,
    ) -> Path:
        del project_dir, isolated, timeout, termination
        wheel_path = work_dir / "pkg-1.0-py3-none-any.whl"
        with zipfile.ZipFile(wheel_path, "w") as zf:
            zf.writestr(zipfile.ZipInfo("pkg/"), "")  # directory entry
            zf.writestr("pkg/__init__.py", b"")
            zf.writestr("pkg-1.0.dist-info/METADATA", b"Metadata-Version: 2.1\n")
        return wheel_path

    monkeypatch.setattr(RUN_BUILD, _fake_run_with_dir_entry)

    result = build_and_read_wheel(tmp_path, timeout=60)

    assert result is not None
    files, cleanup = result
    assert {f.distribution_path for f in files} == {"pkg/__init__.py"}
    cleanup()


@pytest.mark.parametrize("escaping", ["../outside/evil.py", "abs"])
def test_extract_wheel_to_included_files_rejects_zip_slip_entry(
    fake_build: FakeBuildState,
    tmp_path: Path,
    sys_tmp: Path,
    caplog: pytest.LogCaptureFixture,
    escaping: str,
) -> None:
    """A wheel entry whose name escapes the extraction directory (``../``
    segments, or an absolute path) is never written to disk -- skipped
    with exactly one ``WARNING:`` quoting the raw name. A sibling entry in
    the same wheel still extracts normally."""
    if escaping == "abs":
        escaping = (sys_tmp / "abs-evil.py").as_posix()
    fake_build.entries = {escaping: b"evil = 1\n", "pkg/__init__.py": b""}

    with caplog.at_level(logging.WARNING):
        result = build_and_read_wheel(tmp_path, timeout=60)

    assert result is not None
    files, cleanup = result
    assert {f.distribution_path for f in files} == {"pkg/__init__.py"}
    assert not (sys_tmp / "outside").exists()
    assert not (sys_tmp / "abs-evil.py").exists()
    warnings = [r.getMessage() for r in caplog.records]
    assert len(warnings) == 1
    assert f"{escaping!r} has no safe install location -- skipped" in warnings[0]
    cleanup()


def test_extract_wheel_to_included_files_resolve_guard(
    fake_build: FakeBuildState,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    sys_tmp: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The ``resolve()`` guard still blocks an escaping name if the name
    normaliser ever lets one through (defence in depth)."""
    monkeypatch.setattr(
        "pitloom.core._models_wheel_build_and_read.wheel_file_members",
        lambda zf, *_args: [
            WheelFileMember(info, info.orig_filename) for info in zf.infolist()
        ],
    )
    fake_build.entries = {"../outside/evil.py": b"evil = 1\n"}

    with caplog.at_level(logging.WARNING):
        result = build_and_read_wheel(tmp_path, timeout=60)

    # Nothing left to extract: the build counts as a discovery failure.
    assert result is None
    assert not (sys_tmp / "outside").exists()
    assert "resolves outside the extraction directory" in caplog.text


def test_extract_wheel_to_included_files_normalises_member_names(
    fake_build: FakeBuildState, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Non-conforming names (backslash, ``./``) are extracted under their
    install location, with one ``WARNING:`` each -- the same names
    ``read_wheel()`` records, on every OS. Of two members with one install
    location, only the later is extracted and listed, so no entry reports
    bytes another member overwrote."""
    fake_build.entries = {
        "pkg\\mod.py": b"x = 1\n",
        "./pkg/b.py": b"",
        "pkg/c.py": b"first\n",
        "pkg\\c.py": b"second\n",
    }

    with caplog.at_level(logging.WARNING):
        result = build_and_read_wheel(tmp_path, timeout=60)

    assert result is not None
    files, cleanup = result
    by_name = {f.distribution_path: Path(f.path) for f in files}
    assert sorted(f.distribution_path for f in files) == [
        "pkg/b.py",
        "pkg/c.py",
        "pkg/mod.py",
    ]
    assert by_name["pkg/mod.py"].read_bytes() == b"x = 1\n"
    assert by_name["pkg/c.py"].read_bytes() == b"second\n"
    assert len(caplog.records) == 4
    assert "'./pkg/b.py' is non-conforming -- recorded as 'pkg/b.py'" in caplog.text
    cleanup()


@pytest.mark.parametrize(
    ("distribution_path", "expected"),
    [
        ("pkg-1.0.dist-info/METADATA", True),
        ("pkg-1.0.dist-info/RECORD", True),
        ("pkg/dist-info/x.py", False),
        ("pkg-1.0.dist-infoo/x", False),
        ("pkg/__init__.py", False),
        ("pkg\\dist-info\\x", False),
    ],
)
def test_is_dist_info_path(distribution_path: str, expected: bool) -> None:
    """Must match the full ``.dist-info`` suffix on the first path
    segment only (not a substring), and must not treat a
    backslash-separated (non-normalized) input as having any segments at
    all -- its contract is POSIX-only, enforced by the caller."""
    assert is_dist_info_path(distribution_path) is expected


def test_extract_wheel_to_included_files_cross_platform_nested_path(
    fake_build: FakeBuildState, tmp_path: Path
) -> None:
    """A wheel with a nested directory entry (the only legal ZIP form is
    ``/``-separated) must produce a real, readable file and a
    ``/``-separated ``distribution_path`` on whatever OS this test runs
    on -- no ``if sys.platform`` branch should be needed for this to
    pass identically on POSIX and Windows."""
    fake_build.entries = {"pkg/sub/deep/mod.py": b"x = 1\n"}

    result = build_and_read_wheel(tmp_path, timeout=60)

    assert result is not None
    files, cleanup = result
    assert len(files) == 1
    entry = files[0]
    assert entry.distribution_path == "pkg/sub/deep/mod.py"
    assert "\\" not in entry.distribution_path
    assert Path(entry.path).is_file()
    assert Path(entry.path).read_bytes() == b"x = 1\n"
    cleanup()
