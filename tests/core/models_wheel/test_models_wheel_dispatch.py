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
from pitloom.core._models_wheel_types import IncludedFile, warn_discovery_failed
from pitloom.core.models import get_wheel_files
from tests.build_and_read_shared import make_backend_project


def test_get_wheel_files_dispatches_setuptools_backend_to_its_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A project whose backend is detected as ``setuptools`` routes
    through the setuptools discovery module, not the Hatchling
    heuristic."""
    make_backend_project(tmp_path, "setuptools.build_meta")

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

    _root, files, _ = get_wheel_files(tmp_path)

    assert not hatchling_called
    assert [f.distribution_path for f in files] == ["pkg/a.py"]


def test_get_wheel_files_sorts_files_regardless_of_discovery_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The returned file list is sorted by distribution_path even when the
    backend discoverer returns files in a different (e.g.
    filesystem-enumeration-dependent) order, so two runs of one project give
    a bit-for-bit identical SBOM."""
    make_backend_project(tmp_path, "setuptools.build_meta")
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

    _root, files, _ = get_wheel_files(tmp_path)

    assert [f.distribution_path for f in files] == ["a.py", "m.py", "z.py"]


def test_get_wheel_files_setuptools_no_static_config_falls_back_with_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When the setuptools module can't resolve static config (``None``),
    the facade falls back to the Hatchling heuristic and logs a
    warning -- not a silent, unexplained accuracy loss."""
    make_backend_project(tmp_path, "setuptools.build_meta")
    monkeypatch.setattr(
        "pitloom.core._models_wheel_setuptools.discover",
        lambda project_dir, *, pyproject_data=None: None,
    )
    monkeypatch.setattr(WheelBuilder, "recurse_included_files", lambda _self: iter([]))

    with caplog.at_level(logging.WARNING):
        root, files, _ = get_wheel_files(tmp_path)

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
        "from setuptools import setup\n"
        'setup(name="pkg", version="1.0.0", packages=["pkg"])\n',
        encoding="utf-8",
    )

    with caplog.at_level(logging.WARNING):
        root, files, _ = get_wheel_files(tmp_path)

    assert root is None
    assert not files
    assert "no [project] table present" in caplog.text
    assert "Hatchling" not in caplog.text


def test_get_wheel_files_setuptools_build_system_only_skips_doomed_hatchling_attempt(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A pyproject.toml with only [build-system] (metadata and packages both
    declared in setup.py, e.g. real-world certifi) is guaranteed to fail
    Hatchling's own discovery (it requires a [project] table), as with no
    pyproject.toml at all; no redundant "Hatchling"-branded error follows the
    setuptools warning."""
    (tmp_path / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["setuptools"]\n'
        'build-backend = "setuptools.build_meta"\n',
        encoding="utf-8",
    )
    (tmp_path / "setup.py").write_text(
        "from setuptools import setup\n"
        'setup(name="pkg", version="1.0.0", packages=["pkg"])\n',
        encoding="utf-8",
    )

    with caplog.at_level(logging.WARNING):
        root, files, _ = get_wheel_files(tmp_path)

    assert root is None
    assert not files
    assert "no [project] table present" in caplog.text
    assert "Hatchling" not in caplog.text


def test_get_wheel_files_unhandled_backend_no_pyproject_skips_doomed_hatchling(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The no-static-module dispatch path (uv_build today, or any
    unrecognised backend) applies the same "skip a doomed Hatchling attempt"
    guard as its registered-backend sibling (see
    test_get_wheel_files_setuptools_no_pyproject_skips_doomed_hatchling_attempt
    above): Hatchling's WheelBuilder requires a [project] table, so with none
    the fallback is guaranteed to fail, and no second "Hatchling file
    discovery failed" error follows the "not yet backend-aware" one."""
    (tmp_path / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["uv_build"]\nbuild-backend = "uv_build"\n',
        encoding="utf-8",
    )

    with caplog.at_level(logging.WARNING):
        root, files, _ = get_wheel_files(tmp_path)

    assert root is None
    assert not files
    assert "not yet backend-aware" in caplog.text
    assert "file discovery is unsupported for this project" in caplog.text
    # Hatchling never actually runs in this branch -- the warning must
    # not claim it does (a prior version unconditionally said "using
    # Hatchling-based heuristic" even when returning zero files without
    # ever calling Hatchling, which was misleading).
    assert "Hatchling" not in caplog.text


def test_get_wheel_files_unhandled_backend_falls_back_with_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A backend with no dedicated discovery module (e.g. ``uv_build``,
    ahead of its own dedicated support landing) still gets a result via
    the Hatchling heuristic, but now with an explicit warning instead of
    silently risking an inaccurate file list -- closing the gap for
    every unhandled backend, not just setuptools."""
    make_backend_project(tmp_path, "uv_build")

    with caplog.at_level(logging.WARNING):
        root, files, _ = get_wheel_files(tmp_path)

    assert root is None
    assert not files
    assert "uv_build" in caplog.text
    assert "Hatchling" in caplog.text
    assert "--allow-build" not in caplog.text


def test_get_wheel_files_uv_build_fallback_warns_about_wheel_exclude(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A uv_build project whose pyproject.toml declares
    [tool.uv.build-backend] wheel-exclude gets a sharpened WARNING: naming
    the concrete divergence risk and pointing at --allow-build: the case
    where the Hatchling heuristic's file list diverges from a real build's
    (see allow-build-validation.md)."""
    make_backend_project(tmp_path, "uv_build")
    with (tmp_path / "pyproject.toml").open("a", encoding="utf-8") as f:
        f.write('\n[tool.uv.build-backend]\nwheel-exclude = ["pkg/vendored/**"]\n')

    with caplog.at_level(logging.WARNING):
        get_wheel_files(tmp_path)

    assert "[tool.uv.build-backend]" in caplog.text
    assert "--allow-build" in caplog.text


def test_get_wheel_files_uv_build_fallback_no_hint_without_file_filter_keys(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A uv_build project with a [tool.uv.build-backend] table present
    but declaring only non-file-filtering keys (e.g. module-root) must
    not get the sharpened hint (the langfuse
    fixture declares module-root and still matches the heuristic
    exactly), so warning there would be a false alarm)."""
    make_backend_project(tmp_path, "uv_build")
    with (tmp_path / "pyproject.toml").open("a", encoding="utf-8") as f:
        f.write('\n[tool.uv.build-backend]\nmodule-root = ""\n')

    with caplog.at_level(logging.WARNING):
        get_wheel_files(tmp_path)

    assert "uv_build" in caplog.text
    assert "--allow-build" not in caplog.text


def test_get_wheel_files_dispatches_flit_backend_to_its_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A project whose backend is detected as ``flit`` routes through
    the Flit discovery module, not the Hatchling heuristic."""
    make_backend_project(tmp_path, "flit_core.buildapi")

    def _fake_discover(
        project_dir: Path, *, pyproject_data: dict[str, object] | None = None
    ) -> list[IncludedFile]:
        del project_dir, pyproject_data
        return [IncludedFile(path=str(tmp_path / "a.py"), distribution_path="pkg/a.py")]

    (tmp_path / "a.py").write_text("a = 1\n", encoding="utf-8")
    monkeypatch.setattr("pitloom.core._models_wheel_flit.discover", _fake_discover)
    hatchling_called: list[Path] = []

    def _fail_if_called(project_dir: Path) -> list[IncludedFile]:
        hatchling_called.append(project_dir)
        return []

    monkeypatch.setattr(
        "pitloom.core._models_wheel_hatchling.discover", _fail_if_called
    )

    _root, files, _ = get_wheel_files(tmp_path)

    assert not hatchling_called
    assert [f.distribution_path for f in files] == ["pkg/a.py"]


def test_get_wheel_files_flit_discover_accepts_pyproject_data_kwarg(
    tmp_path: Path,
) -> None:
    """Interface uniformity: the Flit discoverer shares
    :class:`~pitloom.core._models_wheel_types.BackendDiscoverer`'s call
    signature, so the dispatch registry needs no per-backend special case.
    Raises ``TypeError`` if the signature drops the keyword."""
    # pylint: disable-next=import-outside-toplevel
    from pitloom.core._models_wheel_flit import discover as discover_flit

    discover_flit(tmp_path, pyproject_data={"tool": {"flit": {}}})


def test_get_wheel_files_dispatches_pdm_backend_to_its_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A project whose backend is detected as ``pdm`` routes through
    the PDM discovery module, not the Hatchling heuristic."""
    make_backend_project(tmp_path, "pdm.backend")

    def _fake_discover(
        project_dir: Path, *, pyproject_data: dict[str, object] | None = None
    ) -> list[IncludedFile]:
        del project_dir, pyproject_data
        return [IncludedFile(path=str(tmp_path / "a.py"), distribution_path="pkg/a.py")]

    (tmp_path / "a.py").write_text("a = 1\n", encoding="utf-8")
    monkeypatch.setattr("pitloom.core._models_wheel_pdm.discover", _fake_discover)
    hatchling_called: list[Path] = []

    def _fail_if_called(project_dir: Path) -> list[IncludedFile]:
        hatchling_called.append(project_dir)
        return []

    monkeypatch.setattr(
        "pitloom.core._models_wheel_hatchling.discover", _fail_if_called
    )

    _root, files, _ = get_wheel_files(tmp_path)

    assert not hatchling_called
    assert [f.distribution_path for f in files] == ["pkg/a.py"]


def test_get_wheel_files_pdm_discover_accepts_pyproject_data_kwarg(
    tmp_path: Path,
) -> None:
    """Interface uniformity: the PDM discoverer shares
    :class:`~pitloom.core._models_wheel_types.BackendDiscoverer`'s call
    signature, so the dispatch registry needs no per-backend special case.
    Raises ``TypeError`` if the signature drops the keyword."""
    # pylint: disable-next=import-outside-toplevel
    from pitloom.core._models_wheel_pdm import discover as discover_pdm

    discover_pdm(tmp_path, pyproject_data={"tool": {"pdm": {}}})


def test_get_wheel_files_dispatches_poetry_backend_to_its_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A project whose backend is detected as ``poetry`` routes through
    the Poetry discovery module, not the Hatchling heuristic."""
    make_backend_project(tmp_path, "poetry.core.masonry.api")

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

    _root, files, _ = get_wheel_files(tmp_path)

    assert not hatchling_called
    assert [f.distribution_path for f in files] == ["pkg/a.py"]


def test_get_wheel_files_poetry_discover_accepts_pyproject_data_kwarg(
    tmp_path: Path,
) -> None:
    """Interface uniformity: the Poetry discoverer shares
    :class:`~pitloom.core._models_wheel_types.BackendDiscoverer`'s call
    signature, so the dispatch registry needs no per-backend special case.
    Raises ``TypeError`` if the signature drops the keyword."""
    # pylint: disable-next=import-outside-toplevel
    from pitloom.core._models_wheel_poetry import discover as discover_poetry

    discover_poetry(tmp_path, pyproject_data={"tool": {"poetry": {"name": "pkg"}}})


def test_get_wheel_files_setuptools_config_present_but_introspection_failed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A project with a real ``[tool.setuptools]`` table (no ``[project]``)
    is statically resolvable: if setuptools' own discover() still returns
    ``None`` (a genuine introspection failure, not "nothing declared"), the
    warning says so rather than claiming "packages only resolvable via an
    imperative setup.py build" (static config *was* present)."""
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
        root, files, _ = get_wheel_files(tmp_path)

    assert root is None
    assert not files
    assert "failed introspection" in caplog.text
    assert "packages only resolvable via an imperative setup.py build" not in (
        caplog.text
    )


@pytest.mark.parametrize(
    ("pyproject_extra", "expected"),
    [
        ('[project]\nname = "pkg"\nversion = "1"\n', "falling back to Hatchling"),
        ("", "file discovery is unsupported"),
    ],
    ids=["project-table", "no-project-table"],
)
def test_a_failed_discovery_is_not_followed_by_a_no_config_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    pyproject_extra: str,
    expected: str,
) -> None:
    """A discoverer that logged ``file discovery failed`` and gave up: the
    fallback line names the failure, never "no static config resolvable"
    (the config was there; discovery failed)."""
    (tmp_path / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["setuptools"]\n'
        'build-backend = "setuptools.build_meta"\n' + pyproject_extra,
        encoding="utf-8",
    )

    def _fails(
        project_dir: Path, *, pyproject_data: dict[str, object] | None = None
    ) -> None:
        warn_discovery_failed(
            logging.getLogger(__name__), "Setuptools", project_dir, ValueError("%")
        )

    monkeypatch.setattr("pitloom.core._models_wheel_setuptools.discover", _fails)

    with caplog.at_level(logging.WARNING):
        get_wheel_files(tmp_path)

    messages = [r.getMessage() for r in caplog.records]
    assert any("Setuptools file discovery failed for" in m for m in messages)
    assert any(expected in m and "discovery failed in" in m for m in messages)
    assert not any("No static" in m for m in messages)


def test_a_stale_failure_report_does_not_reword_the_next_discovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failure reported earlier on the thread must not make a later
    "found nothing declared" discoverer say it failed."""
    warn_discovery_failed(
        logging.getLogger(__name__), "Flit", tmp_path, ValueError("x")
    )
    (tmp_path / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["setuptools"]\n'
        'build-backend = "setuptools.build_meta"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "pitloom.core._models_wheel_setuptools.discover",
        lambda project_dir, *, pyproject_data=None: None,
    )
    with caplog.at_level(logging.WARNING):
        caplog.clear()
        get_wheel_files(tmp_path)

    assert "No static setuptools config resolvable" in caplog.text
    assert "discovery failed in" not in caplog.text


def test_get_wheel_files_hatchling_discover_accepts_pyproject_data_kwarg(
    tmp_path: Path,
) -> None:
    """Every backend's ``discover()`` shares
    :class:`~pitloom.core._models_wheel_types.BackendDiscoverer`'s call
    signature, so the dispatch registry needs no per-backend special case;
    Hatchling, the implicit (non-registry) fallback, does not use the
    argument itself."""
    # Raises TypeError if the signature drops the keyword.
    discover_hatchling(tmp_path, pyproject_data={"project": {"name": "pkg"}})


def test_get_wheel_files_relative_project_dir_keeps_physical_path_relative(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A relative *project_dir* (as the public library API accepts:
    ``generate_project_sbom("myproj")`` never resolves it) does not leak an
    absolute, machine-local path into ``ProjectFile.physical_path``;
    ``Path(source).relative_to(project_dir)`` always raises for an absolute
    *source* against a relative *project_dir*."""
    make_backend_project(tmp_path, "setuptools.build_meta")
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

    _root, files, _ = get_wheel_files(relative_project_dir)

    assert len(files) == 1
    assert not Path(files[0].physical_path).is_absolute()
    assert files[0].physical_path == "a.py"


def test_get_wheel_files_assume_backend_skips_detection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A caller that knows the backend by construction (e.g. the Hatchling
    build hook) can pass ``assume_backend`` to skip the ``pyproject.toml``
    parse and ``detect_build_backend()`` call instead of re-detecting."""
    detect_calls: list[Path] = []
    read_calls: list[Path] = []

    def _spy_detect(project_dir: Path, **_kwargs: object) -> str | None:
        detect_calls.append(project_dir)
        return "hatchling"

    # The explicit None is the "no data" signal; mypy requires the return.
    # pylint: disable-next=useless-return
    def _spy_read(project_dir: Path) -> dict[str, object] | None:
        read_calls.append(project_dir)
        return None

    monkeypatch.setattr(
        "pitloom.extract.project.setuptools.detect_build_backend", _spy_detect
    )
    monkeypatch.setattr(
        "pitloom.extract.project.setuptools.read_pyproject_toml", _spy_read
    )
    monkeypatch.setattr(WheelBuilder, "recurse_included_files", lambda _self: iter([]))

    get_wheel_files(tmp_path, assume_backend="hatchling")

    assert not detect_calls
    assert not read_calls
