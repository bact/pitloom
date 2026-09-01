# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for get_wheel_files() backend dispatch and fallback-warning
behavior.

See also: tests/core/models_wheel/test_models_wheel_files.py for
file-header scanning and content-type detection tests;
tests/core/models_wheel/test_models_wheel_setuptools.py for the
setuptools discovery module's own tests;
tests/core/models_wheel/test_models_wheel_dispatch_lock.py for the
discovery-lock concurrency tests split out of this file.
"""

import logging
from pathlib import Path

import pytest
from hatchling.builders.wheel import WheelBuilder

from pitloom.core._models_wheel_hatchling import discover as discover_hatchling
from pitloom.core._models_wheel_types import IncludedFile
from pitloom.core.models import get_wheel_files


def _make_backend_project(tmp_path: Path, build_backend: str) -> None:
    (tmp_path / "pyproject.toml").write_text(
        f'[build-system]\nrequires = ["{build_backend.split(".", maxsplit=1)[0]}"]\n'
        f'build-backend = "{build_backend}"\n\n'
        '[project]\nname = "pkg"\nversion = "1.0.0"\n',
        encoding="utf-8",
    )


def test_get_wheel_files_dispatches_setuptools_backend_to_its_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A project whose backend is detected as ``setuptools`` routes
    through the setuptools discovery module, not the Hatchling
    heuristic."""
    _make_backend_project(tmp_path, "setuptools.build_meta")

    def _fake_discover(
        project_dir: Path, *, pyproject_data: dict[str, object] | None = None
    ) -> list[IncludedFile]:
        del project_dir, pyproject_data
        return [IncludedFile(path=str(tmp_path / "a.py"), distribution_path="pkg/a.py")]

    (tmp_path / "a.py").write_text("a = 1\n", encoding="utf-8")
    monkeypatch.setattr(
        "pitloom.core._models_wheel_setuptools.discover", _fake_discover
    )
    hatchling_called: list[Path] = []

    def _fail_if_called(project_dir: Path) -> list[IncludedFile]:
        hatchling_called.append(project_dir)
        return []

    monkeypatch.setattr(
        "pitloom.core._models_wheel_hatchling.discover", _fail_if_called
    )

    _root, files = get_wheel_files(tmp_path)

    assert not hatchling_called
    assert [f.distribution_path for f in files] == ["pkg/a.py"]


def test_get_wheel_files_sorts_files_regardless_of_discovery_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: the returned file list must be sorted by
    distribution_path even when the backend discoverer returns files in
    a different (e.g. filesystem-enumeration-dependent, unsorted) order
    -- both runs of "the same project" must produce a bit-for-bit
    identical SBOM regardless of discovery order."""
    _make_backend_project(tmp_path, "setuptools.build_meta")
    (tmp_path / "z.py").write_text("z = 1\n", encoding="utf-8")
    (tmp_path / "a.py").write_text("a = 1\n", encoding="utf-8")
    (tmp_path / "m.py").write_text("m = 1\n", encoding="utf-8")

    def _unsorted_discover(
        project_dir: Path, *, pyproject_data: dict[str, object] | None = None
    ) -> list[IncludedFile]:
        del pyproject_data
        # Deliberately not alphabetical -- a discoverer is not expected
        # to sort its own output; get_wheel_files() must do it.
        return [
            IncludedFile(path=str(project_dir / "z.py"), distribution_path="z.py"),
            IncludedFile(path=str(project_dir / "a.py"), distribution_path="a.py"),
            IncludedFile(path=str(project_dir / "m.py"), distribution_path="m.py"),
        ]

    monkeypatch.setattr(
        "pitloom.core._models_wheel_setuptools.discover", _unsorted_discover
    )

    _root, files = get_wheel_files(tmp_path)

    assert [f.distribution_path for f in files] == ["a.py", "m.py", "z.py"]


def test_get_wheel_files_setuptools_no_static_config_falls_back_with_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When the setuptools module can't resolve static config (``None``),
    the facade falls back to the Hatchling heuristic and logs a
    warning -- not a silent, unexplained accuracy regression."""
    _make_backend_project(tmp_path, "setuptools.build_meta")
    monkeypatch.setattr(
        "pitloom.core._models_wheel_setuptools.discover",
        lambda project_dir, *, pyproject_data=None: None,
    )
    monkeypatch.setattr(WheelBuilder, "recurse_included_files", lambda _self: iter([]))

    with caplog.at_level(logging.WARNING):
        root, files = get_wheel_files(tmp_path)

    assert root is None
    assert not files
    assert "setuptools" in caplog.text
    assert "Hatchling" in caplog.text


def test_get_wheel_files_setuptools_no_pyproject_skips_doomed_hatchling_attempt(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A setup.py-only project (no pyproject.toml at all) is guaranteed
    to fail Hatchling's own discovery too (it requires a [project]
    table) -- skip that doomed attempt and its confusing
    Hatchling-branded error, logging one clear warning instead of two."""
    (tmp_path / "setup.py").write_text(
        'from setuptools import setup\nsetup(name="pkg", version="1.0.0")\n',
        encoding="utf-8",
    )

    with caplog.at_level(logging.WARNING):
        root, files = get_wheel_files(tmp_path)

    assert root is None
    assert not files
    assert "no [project] table present" in caplog.text
    assert "Hatchling" not in caplog.text


def test_get_wheel_files_setuptools_build_system_only_skips_doomed_hatchling_attempt(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Regression: a pyproject.toml with only [build-system] (metadata
    and packages both declared imperatively in setup.py -- e.g. real-world
    certifi) is *also* guaranteed to fail Hatchling's own discovery (it
    requires a [project] table), same as no pyproject.toml at all --
    the file-existence-only check previously missed this case, producing
    a redundant, confusing "Hatchling"-branded error on top of the
    setuptools warning."""
    (tmp_path / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["setuptools"]\n'
        'build-backend = "setuptools.build_meta"\n',
        encoding="utf-8",
    )
    (tmp_path / "setup.py").write_text(
        'from setuptools import setup\nsetup(name="pkg", version="1.0.0")\n',
        encoding="utf-8",
    )

    with caplog.at_level(logging.WARNING):
        root, files = get_wheel_files(tmp_path)

    assert root is None
    assert not files
    assert "no [project] table present" in caplog.text
    assert "Hatchling" not in caplog.text


def test_get_wheel_files_unhandled_backend_falls_back_with_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A backend with no dedicated discovery module (e.g. PDM-Backend,
    ahead of its own dedicated support landing) still gets a result via
    the Hatchling heuristic, but now with an explicit warning instead of
    silently risking an inaccurate file list -- closing the gap for
    every unhandled backend, not just setuptools."""
    _make_backend_project(tmp_path, "pdm.backend")

    with caplog.at_level(logging.WARNING):
        root, files = get_wheel_files(tmp_path)

    assert root is None
    assert not files
    assert "pdm" in caplog.text
    assert "Hatchling" in caplog.text


def test_get_wheel_files_dispatches_poetry_backend_to_its_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A project whose backend is detected as ``poetry`` routes through
    the Poetry discovery module, not the Hatchling heuristic."""
    _make_backend_project(tmp_path, "poetry.core.masonry.api")

    def _fake_discover(
        project_dir: Path, *, pyproject_data: dict[str, object] | None = None
    ) -> list[IncludedFile]:
        del project_dir, pyproject_data
        return [IncludedFile(path=str(tmp_path / "a.py"), distribution_path="pkg/a.py")]

    (tmp_path / "a.py").write_text("a = 1\n", encoding="utf-8")
    monkeypatch.setattr("pitloom.core._models_wheel_poetry.discover", _fake_discover)
    hatchling_called: list[Path] = []

    def _fail_if_called(project_dir: Path) -> list[IncludedFile]:
        hatchling_called.append(project_dir)
        return []

    monkeypatch.setattr(
        "pitloom.core._models_wheel_hatchling.discover", _fail_if_called
    )

    _root, files = get_wheel_files(tmp_path)

    assert not hatchling_called
    assert [f.distribution_path for f in files] == ["pkg/a.py"]


def test_get_wheel_files_poetry_discover_accepts_pyproject_data_kwarg(
    tmp_path: Path,
) -> None:
    """Interface-uniformity regression: the Poetry discoverer must share
    :class:`~pitloom.core._models_wheel_types.BackendDiscoverer`'s call
    signature so the dispatch registry never needs a per-backend special
    case. Raises ``TypeError`` if the signature ever drops the keyword."""
    # pylint: disable-next=import-outside-toplevel
    from pitloom.core._models_wheel_poetry import discover as discover_poetry

    discover_poetry(tmp_path, pyproject_data={"tool": {"poetry": {"name": "pkg"}}})


def test_get_wheel_files_setuptools_config_present_but_introspection_failed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Regression: a project with a real ``[tool.setuptools]`` table (no
    ``[project]``) is statically resolvable -- if setuptools' own
    discover() still returns ``None`` (a genuine introspection failure,
    not "nothing declared"), the warning must say so, not claim
    "packages only resolvable via an imperative setup.py build" (false
    here: static config *was* present, something else went wrong)."""
    (tmp_path / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["setuptools"]\n'
        'build-backend = "setuptools.build_meta"\n\n'
        '[tool.setuptools]\npackages = ["pkg"]\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "pitloom.core._models_wheel_setuptools.discover",
        lambda project_dir, *, pyproject_data=None: None,
    )

    with caplog.at_level(logging.WARNING):
        root, files = get_wheel_files(tmp_path)

    assert root is None
    assert not files
    assert "failed introspection" in caplog.text
    assert "packages only resolvable via an imperative setup.py build" not in (
        caplog.text
    )


def test_get_wheel_files_hatchling_discover_accepts_pyproject_data_kwarg(
    tmp_path: Path,
) -> None:
    """Interface-uniformity regression: every backend's ``discover()``
    must share :class:`~pitloom.core._models_wheel_types.BackendDiscoverer`'s
    call signature so the dispatch registry never needs a per-backend
    special case -- including Hatchling, which is the implicit
    (non-registry) fallback and doesn't use the argument itself."""
    # Raises TypeError if the signature ever drops the keyword again.
    discover_hatchling(tmp_path, pyproject_data={"project": {"name": "pkg"}})


def test_get_wheel_files_relative_project_dir_keeps_physical_path_relative(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: a relative *project_dir* (as the public library API
    accepts -- ``generate_project_sbom("myproj")`` never resolves it)
    must not leak an absolute, machine-local path into
    ``ProjectFile.physical_path``. Before the fix, ``Path(source)
    .relative_to(project_dir)`` always raises for an absolute *source*
    against a relative *project_dir*, silently falling back to the
    absolute form."""
    _make_backend_project(tmp_path, "setuptools.build_meta")
    (tmp_path / "a.py").write_text("a = 1\n", encoding="utf-8")

    def _fake_discover(
        project_dir: Path, *, pyproject_data: dict[str, object] | None = None
    ) -> list[IncludedFile]:
        del pyproject_data
        # Mirrors the real setuptools discover(): resolved, absolute paths.
        return [
            IncludedFile(
                path=str((project_dir / "a.py").resolve()),
                distribution_path="pkg/a.py",
            )
        ]

    monkeypatch.setattr(
        "pitloom.core._models_wheel_setuptools.discover", _fake_discover
    )
    monkeypatch.chdir(tmp_path.parent)
    relative_project_dir = Path(tmp_path.name)

    _root, files = get_wheel_files(relative_project_dir)

    assert len(files) == 1
    assert not Path(files[0].physical_path).is_absolute()
    assert files[0].physical_path == "a.py"


def test_get_wheel_files_assume_backend_skips_detection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: a caller that already knows the backend by
    construction (e.g. the Hatchling build hook, which is always
    Hatchling) can pass ``assume_backend`` to skip the
    ``pyproject.toml`` parse and ``detect_build_backend()`` call
    entirely, instead of paying for a redundant re-detection of
    something already known."""
    detect_calls: list[Path] = []
    read_calls: list[Path] = []

    def _spy_detect(project_dir: Path, **_kwargs: object) -> str | None:
        detect_calls.append(project_dir)
        return "hatchling"

    def _spy_read(project_dir: Path) -> dict[str, object] | None:
        read_calls.append(project_dir)
        return None

    monkeypatch.setattr("pitloom.extract._setuptools.detect_build_backend", _spy_detect)
    monkeypatch.setattr("pitloom.extract._setuptools.read_pyproject_toml", _spy_read)
    monkeypatch.setattr(WheelBuilder, "recurse_included_files", lambda _self: iter([]))

    get_wheel_files(tmp_path, assume_backend="hatchling")

    assert not detect_calls
    assert not read_calls
