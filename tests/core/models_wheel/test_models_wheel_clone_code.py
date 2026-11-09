# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""In a Git URL's clone, the file discovery runs none of the repository's
own code: a Hatchling metadata hook, a setuptools ``cmdclass`` or ``attr``
version, a PDM build hook or ``run-setuptools`` is ignored, said in one
``config-unsafe/build-code`` ``WARNING:``, and the files still come from the
static settings. A local project runs them, as its backend would.

Each hostile project's code only writes a marker file inside ``tmp_path``.

See also: :mod:`tests.core.models_wheel.test_models_wheel_outside_clone`
(files out of the clone).
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from pitloom.core import _models_wheel_pdm
from pitloom.core.clone_mark import reading_remote_clone
from pitloom.core.models import get_wheel_files
from pitloom.logging_config import CODE_ATTR

_CODE = "config-unsafe/build-code"
_HB = b'[build-system]\nrequires = ["hatchling"]\nbuild-backend = "hatchling.build"\n'
_ST = (
    b'[build-system]\nrequires = ["setuptools"]\n'
    b'build-backend = "setuptools.build_meta"\n'
)
_PD = (
    b'[build-system]\nrequires = ["pdm-backend"]\n'
    b'build-backend = "pdm.backend"\n[project]\nname = "demo"\nversion = "1"\n'
)
_META_HOOK = (
    b"from hatchling.metadata.plugin.interface import MetadataHookInterface\n"
    b"class Hook(MetadataHookInterface):\n"
    b"    def update(self, metadata):\n        pass\n"
)
_PDM_HOOK = b"def pdm_build_update_files(context, files):\n    pass\n"
_DEMO = {"demo/__init__.py": b""}

#: (id, files with "MARK" where the marker-writing line goes, the FILE and
#: settings the warning names, the wheel paths the clone still lists).
_VECTORS = [
    (
        "hatch-hook",
        {
            "pyproject.toml": _HB + b'[project]\nname = "demo"\nversion = "1"\n'
            b"[tool.hatch.metadata.hooks.custom]\n",
            "hatch_build.py": b"MARK" + _META_HOOK,
            **_DEMO,
        },
        "FILE=pyproject.toml",
        "tool.hatch.metadata.hooks",
        ["demo/__init__.py"],
    ),
    (
        "hatch-hook-path-and-version-code",
        {
            "pyproject.toml": _HB + b'[project]\nname = "demo"\n'
            b'dynamic = ["version"]\n'
            b'[tool.hatch.version]\nsource = "code"\npath = "v.py"\n'
            b'[tool.hatch.metadata.hooks.custom]\npath = "x/hook.py"\n',
            "x/hook.py": b"MARK" + _META_HOOK,
            "v.py": b"MARK__version__ = '1'\n",
            **_DEMO,
        },
        "FILE=pyproject.toml",
        "tool.hatch.metadata.hooks",
        ["demo/__init__.py"],
    ),
    (
        "hatch-toml-hook",
        {
            "pyproject.toml": _HB + b'[project]\nname = "demo"\nversion = "1"\n',
            "hatch.toml": b"[metadata.hooks.custom]\n",
            "hatch_build.py": b"MARK" + _META_HOOK,
            **_DEMO,
        },
        "FILE=hatch.toml",
        "metadata.hooks",
        ["demo/__init__.py"],
    ),
    (
        "setuptools-attr",
        {
            "pyproject.toml": _ST + b'[project]\nname = "demo"\n'
            b'dynamic = ["version"]\n'
            b'[tool.setuptools.dynamic]\nversion = {attr = "demo.v"}\n',
            "demo/__init__.py": b"MARKv = str(1)\n",
        },
        "FILE=pyproject.toml",
        "tool.setuptools.dynamic.version",
        ["demo/__init__.py"],
    ),
    (
        "setuptools-cmdclass",
        {
            "pyproject.toml": _ST + b'[project]\nname = "demo"\nversion = "1"\n'
            b'[tool.setuptools]\ncmdclass = {build_py = "demo.c.X"}\n',
            "demo/__init__.py": b"",
            "demo/c.py": b"MARKfrom setuptools.command.build_py import build_py as X\n",
        },
        "FILE=pyproject.toml",
        "tool.setuptools.cmdclass",
        ["demo/__init__.py", "demo/c.py"],
    ),
    (
        "setup-cfg-attr-and-cmdclass",
        {
            "setup.cfg": b"[metadata]\nname = demo\nversion = attr: demo.v\n"
            b"[options]\npackages = demo\ncmdclass =\n    build_py = demo.c.X\n",
            "setup.py": b"from setuptools import setup\nsetup()\n",
            "demo/__init__.py": b"MARKv = str(1)\n",
            "demo/c.py": b"MARKfrom setuptools.command.build_py import build_py as X\n",
        },
        "FILE=setup.cfg",
        "metadata.version, options.cmdclass",
        ["demo/__init__.py", "demo/c.py"],
    ),
    (
        "pdm-build-py",
        {"pyproject.toml": _PD, "pdm_build.py": b"MARK" + _PDM_HOOK, **_DEMO},
        "FILE=pyproject.toml",
        "tool.pdm.build.custom-hook",
        ["demo/__init__.py"],
    ),
    (
        "pdm-custom-hook",
        {
            "pyproject.toml": _PD + b'[tool.pdm.build]\ncustom-hook = "x/h.py"\n',
            "x/h.py": b"MARK" + _PDM_HOOK,
            **_DEMO,
        },
        "FILE=pyproject.toml",
        "tool.pdm.build.custom-hook",
        ["demo/__init__.py"],
    ),
]

#: Run by a local discovery in a subprocess: its local control is its own
#: test.
_RUN_SETUPTOOLS = (
    "pdm-run-setuptools",
    {
        "pyproject.toml": _PD + b"[tool.pdm.build]\nrun-setuptools = true\n",
        "setup.py": b"MARKfrom setuptools import setup\nsetup()\n",
        **_DEMO,
    },
    "FILE=pyproject.toml",
    "tool.pdm.build.run-setuptools",
    ["demo/__init__.py"],
)

#: Settings that name code a file discovery never runs: nothing is
#: neutralised, nothing said, nothing run, in a clone or not.
_INERT = [
    (
        "hatch-build-hook",
        {
            "pyproject.toml": _HB + b'[project]\nname = "demo"\nversion = "1"\n'
            b"[tool.hatch.build.targets.wheel.hooks.custom]\n",
            "hatch_build.py": b"MARKfrom hatchling.builders.hooks.plugin."
            b"interface import BuildHookInterface\n"
            b"class Hook(BuildHookInterface):\n    pass\n",
            **_DEMO,
        },
    ),
    (
        "hatch-version-code",
        {
            "pyproject.toml": _HB + b'[project]\nname = "demo"\n'
            b'dynamic = ["version"]\n'
            b'[tool.hatch.version]\nsource = "code"\npath = "v.py"\n',
            "v.py": b"MARK__version__ = '1'\n",
            **_DEMO,
        },
    ),
    (
        "pdm-version-call",
        {
            "pyproject.toml": _PD.replace(b'version = "1"\n', b"")
            + b'dynamic = ["version"]\n'
            b'[tool.pdm.version]\nsource = "call"\ngetter = "demo.v:get"\n',
            "demo/__init__.py": b"",
            "demo/v.py": b"MARKdef get():\n    return '1'\n",
        },
    ),
    (
        "flit-dynamic-version",
        {
            "pyproject.toml": b'[build-system]\nrequires = ["flit_core"]\n'
            b'build-backend = "flit_core.buildapi"\n'
            b'[project]\nname = "demo"\ndynamic = ["version", "description"]\n',
            "demo/__init__.py": b'"""Doc."""\nMARKimport os\n'
            b'__version__ = os.sep and "1"\n',
        },
    ),
    (
        "setuptools-attr-literal",
        {
            "pyproject.toml": _ST + b'[project]\nname = "demo"\n'
            b'dynamic = ["version"]\n'
            b'[tool.setuptools.dynamic]\nversion = {attr = "demo.v"}\n',
            "demo/__init__.py": b"v = '1'\n",
        },
    ),
]


def _write(root: Path, files: dict[str, bytes], marker: Path) -> Path:
    line = f"import pathlib; pathlib.Path({str(marker)!r}).write_text('x')\n"
    for name, content in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(content.replace(b"MARK", line.encode()))
    return root


def _project_modules() -> set[str]:
    """The test projects' modules imported so far (``demo``, ``demo.*``)."""
    return {name for name in sys.modules if name.partition(".")[0] == "demo"}


def _discover(root: Path, *, clone: bool) -> list[str]:
    """The wheel paths *root* lists, read as a clone's or not; a ``demo``
    module another project imported is not reused, nor is one left behind
    (setuptools reads an ``attr`` from ``sys.modules`` first)."""
    saved = {name: sys.modules.pop(name) for name in _project_modules()}
    try:
        if clone:
            with reading_remote_clone(str(root)):
                _merkle, files, cleanup = get_wheel_files(root)
        else:
            _merkle, files, cleanup = get_wheel_files(root)
    finally:
        for name in _project_modules():
            del sys.modules[name]
        sys.modules.update(saved)
    cleanup()
    return [f.distribution_path for f in files]


def _said(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if getattr(r, CODE_ATTR, None) == _CODE and r.levelno == logging.WARNING
    ]


@pytest.mark.parametrize(
    ("files", "subject", "settings", "listed"),
    [v[1:] for v in (*_VECTORS, _RUN_SETUPTOOLS)],
    ids=[v[0] for v in (*_VECTORS, _RUN_SETUPTOOLS)],
)
def test_the_clone_runs_no_build_code_and_still_lists_its_files(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    files: dict[str, bytes],
    subject: str,
    settings: str,
    listed: list[str],
) -> None:
    marker = tmp_path / "RAN"
    root = _write(tmp_path / "clone", files, marker)
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        found = _discover(root, clone=True)
    assert not marker.exists()
    assert found == listed
    assert "discovery failed" not in caplog.text
    assert _said(caplog) == [
        f"{subject}: build-time code of the downloaded repository is not run; "
        f"{settings} ignored"
    ]


@pytest.mark.parametrize(
    ("files", "listed"),
    [(v[1], v[4]) for v in _VECTORS],
    ids=[v[0] for v in _VECTORS],
)
def test_a_local_project_runs_its_build_code_as_before(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    files: dict[str, bytes],
    listed: list[str],
) -> None:
    """Out of a clone the backend runs what it always ran."""
    marker = tmp_path / "RAN"
    root = _write(tmp_path / "local", files, marker)
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        found = _discover(root, clone=False)
    assert marker.exists()
    assert found == listed
    assert not _said(caplog)


def test_a_local_pdm_project_runs_its_setup_py_as_before(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The control of ``run-setuptools``: out of a clone, PDM runs
    ``setup.py`` while it lists the files."""
    marker = tmp_path / "RAN"
    root = _write(tmp_path / "local", _RUN_SETUPTOOLS[1], marker)
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        found = _discover(root, clone=False)
    assert marker.exists()
    assert "demo/__init__.py" in found
    assert not _said(caplog)


@pytest.mark.parametrize("clone", [True, False], ids=["clone", "local"])
@pytest.mark.parametrize("files", [v[1] for v in _INERT], ids=[v[0] for v in _INERT])
def test_code_no_discovery_runs_stays_unrun_and_unsaid(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    files: dict[str, bytes],
    clone: bool,
) -> None:
    marker = tmp_path / "RAN"
    root = _write(tmp_path / "project", files, marker)
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        found = _discover(root, clone=clone)
    assert not marker.exists()
    assert "demo/__init__.py" in found
    assert not _said(caplog)


@pytest.mark.parametrize("clone", [True, False], ids=["clone", "local"])
def test_the_pdm_version_reader_loads_no_build_hook_in_a_clone(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, clone: bool
) -> None:
    """Reading a ``file`` version makes a PDM builder too, which imports the
    project's ``pdm_build.py``: not in a clone."""
    # pylint: disable-next=import-outside-toplevel
    from pitloom.extract.project import read_project

    marker = tmp_path / "RAN"
    root = _write(
        tmp_path / "project",
        {
            "pyproject.toml": _PD.replace(b'version = "1"\n', b"")
            + b'dynamic = ["version"]\n'
            b'[tool.pdm.version]\nsource = "file"\npath = "demo/__init__.py"\n',
            "pdm_build.py": b"MARK" + _PDM_HOOK,
            "demo/__init__.py": b'__version__ = "1.2"\n',
        },
        marker,
    )
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        if clone:
            with reading_remote_clone(str(root)):
                metadata, _config, _lock = read_project(root)
        else:
            metadata, _config, _lock = read_project(root)
    assert metadata.version == "1.2"
    assert marker.exists() is not clone
    assert len(_said(caplog)) == clone


def test_an_installed_pdm_plugins_hooks_still_run_in_a_clone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only the repository's own hook is left out: a plugin's hook, a class
    or a module, is installed code and runs as it would locally."""
    called: list[str] = []

    class ClassHook:  # pylint: disable=too-few-public-methods
        """A hook class, made once per builder."""

        def pdm_build_update_files(self, _context: object, _files: object) -> None:
            called.append("class")

    module_hook = SimpleNamespace(
        pdm_build_update_files=lambda _context, _files: called.append("module")
    )
    plugins = [
        SimpleNamespace(load=lambda: ClassHook),
        SimpleNamespace(load=lambda: module_hook),
    ]
    loaded_in: list[str] = []

    def entry_points(*, group: str) -> list[SimpleNamespace]:
        loaded_in.append(os.getcwd())
        return plugins if group == "pdm.build.hook" else []

    monkeypatch.setattr(_models_wheel_pdm, "entry_points", entry_points)
    marker = tmp_path / "RAN"
    root = _write(
        tmp_path / "clone", {v[0]: v[1] for v in _VECTORS}["pdm-build-py"], marker
    )
    assert _discover(root, clone=True) == ["demo/__init__.py"]
    assert called == ["class", "module"] and not marker.exists()
    # Loaded before the working directory is the clone.
    assert loaded_in and str(root) not in loaded_in
