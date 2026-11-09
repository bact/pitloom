# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""What a clone's setuptools configuration leaves out: a file pattern, a
package or module path or a ``file:`` directive that can reach out of the
clone or into its ``.git``, a ``setup.cfg`` ``[global]`` section; what it
still resolves; and a setuptools without a private piece the clone's path
calls.

See also: :mod:`tests.core.models_wheel.test_models_wheel_outside_clone`
(the settings left out, end to end) and
:mod:`tests.core.models_wheel.test_models_wheel_clone_code` (the code).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest
from setuptools.config import pyprojecttoml
from setuptools.dist import Distribution

from pitloom.core import _models_wheel_setuptools_clone as setuptools_clone
from pitloom.core._models_wheel_setuptools import discover
from pitloom.core.clone_mark import reading_remote_clone
from pitloom.logging_config import CODE_ATTR

_ST = (
    b'[build-system]\nrequires = ["setuptools"]\n'
    b'build-backend = "setuptools.build_meta"\n'
    b'[project]\nname = "demo"\nversion = "1"\n'
)
_CFG = b"[metadata]\nname = demo\nversion = 1\n[options]\npackages = demo\n"
_SETUP_PY = b"from setuptools import setup\nsetup()\n"


@pytest.mark.parametrize(
    ("pattern", "out"),
    [
        ("/etc/*", True),
        ("~/x", True),
        ("C:x", True),
        ("C:\\x", True),
        ("\\\\srv\\sh\\x", True),
        ("\\\\?\\C:\\x", True),
        ("a/../../b", True),
        ("a\\..\\b", True),
        ("..", True),
        (".git/*", True),
        ("x/.GIT/y", True),
        ("*.txt", False),
        ("data/**/*.bin", False),
        ("a..b/.c", False),
        (".github/*", False),
        (".gitignore", False),
    ],
    ids=[
        "absolute",
        "home",
        "drive",
        "drive-backslash",
        "unc",
        "unc-device",
        "dotdot",
        "backslash",
        "up",
        "git",
        "git-case",
        "glob",
        "deep",
        "dots",
        "github",
        "gitignore",
    ],
)
def test_a_pattern_that_can_reach_out_is_left_out(
    tmp_path: Path, pattern: str, out: bool
) -> None:
    with reading_remote_clone(str(tmp_path)):
        # pylint: disable-next=protected-access
        ignored = setuptools_clone._Ignored(tmp_path)
        assert ignored.pattern_outside(pattern) is out
    assert ignored.entries == ([pattern] if out else [])


@pytest.fixture(name="clone")
def _clone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A clone at ``clone`` (the working directory) with ``demo``,
    ``LICENSE`` and a ``.git/config``, beside ``host`` with a secret, a
    package and a module."""
    host = tmp_path / "host"
    (host / "pkg" / "hostpkg").mkdir(parents=True)
    (host / "pkg" / "hostpkg" / "__init__.py").write_bytes(b"")
    (host / "secret.txt").write_bytes(b"HOSTSECRET\n")
    (host / "hostmod.py").write_bytes(b"")
    root = tmp_path / "clone"
    (root / "demo").mkdir(parents=True)
    (root / "demo" / "__init__.py").write_bytes(b'v = "1"\n')
    (root / "LICENSE").write_bytes(b"MIT\n")
    (root / "secret.txt").write_bytes(b"CLONE\n")
    (root / ".git").mkdir()
    (root / ".git" / "config").write_bytes(b"url = https://u:SECRET@h/r\n")
    monkeypatch.chdir(root)
    return root


def _host(clone: Path) -> str:
    return (clone.parent / "host").as_posix()


class _Records(logging.Handler):
    """The records a logger hands it."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def _apply_cfg(clone: Path, text: bytes) -> tuple[Any, list[str]]:
    """*text* as the clone's ``setup.cfg`` applied to a new distribution,
    and the ``WARNING:`` lines said."""
    (clone / "setup.cfg").write_bytes(text.replace(b"HOST", _host(clone).encode()))
    dist = Distribution()
    handler = _Records()
    logger = logging.getLogger("pitloom")
    logger.addHandler(handler)
    try:
        with reading_remote_clone(str(clone)):
            setuptools_clone.apply_setup_cfg(dist, clone / "setup.cfg", clone)
    finally:
        logger.removeHandler(handler)
    said = [r.getMessage() for r in handler.records if r.levelno >= logging.WARNING]
    return dist, said


@pytest.mark.parametrize(
    "glob",
    [
        b"[global]\nsrc_root = HOST\ncommand_packages = evil\nnew_attr = x\n",
        b"[global]\nsrc_root = HOST\n[egg_info]\negg_base = HOST\n",
    ],
    ids=["global", "and-command"],
)
def test_a_global_section_sets_nothing_on_the_distribution(
    clone: Path, glob: bytes
) -> None:
    dist, said = _apply_cfg(
        clone,
        glob
        + _CFG.replace(
            b"version = 1", b"version = 1\nlong_description = file: secret.txt"
        )
        + b"[options.packages.find]\nwhere = pkg\n",
    )
    assert dist.src_root is None
    assert dist.command_packages is None
    assert not hasattr(dist, "new_attr")
    assert set(dist.command_options) <= {"metadata", "options", "options.packages.find"}
    assert dist.metadata.long_description == "CLONE\n"
    assert said[0] == (
        "FILE=setup.cfg: build-time code of the downloaded repository is not "
        "run; global ignored"
    )


def test_a_file_directive_out_of_the_clone_or_in_git_is_not_read(
    clone: Path,
) -> None:
    dist, said = _apply_cfg(
        clone,
        b"[metadata]\nname = demo\nversion = file: .git/config\n"
        b"long_description = file: LICENSE, HOST/secret.txt\n"
        b"[options]\npackages = demo\ninstall_requires = file: .git/config\n",
    )
    assert dist.metadata.long_description == "MIT\n"
    assert dist.metadata.version != "url = https://u:SECRET@h/r"
    assert not dist.install_requires
    assert said == [
        f"FILE={entry}: outside the downloaded repository; not read"
        for entry in sorted((".git/config", f"{_host(clone)}/secret.txt"))
    ]


@pytest.mark.parametrize(
    ("packages", "left"),
    [
        (
            b"packages =\n  demo\n  HOST/pkg/hostpkg\npy_modules = HOST/hostmod\n",
            ["HOST/hostmod", "HOST/pkg/hostpkg"],
        ),
        (b"packages = HOST/pkg/hostpkg, demo\n", ["HOST/pkg/hostpkg"]),
        (b"packages = find:\n", []),
    ],
    ids=["lines", "commas", "find"],
)
def test_a_package_or_module_path_out_of_the_clone_is_left_out(
    clone: Path, packages: bytes, left: list[str]
) -> None:
    dist, said = _apply_cfg(
        clone, b"[metadata]\nname = demo\nversion = 1\n[options]\n" + packages
    )
    assert dist.packages == ["demo"]
    assert not dist.py_modules
    assert said == [
        f"FILE={entry.replace('HOST', _host(clone))}: outside the downloaded "
        "repository; not read"
        for entry in left
    ]


def test_each_entry_of_a_multi_line_value_is_filtered(clone: Path) -> None:
    """Split by line, not by comma: the entry after the first is checked."""
    options: dict[str, Any] = {
        "options.package_data": {"demo": ("s", "ok/*\n  ../x")},
        "options.data_files": {"share": ("s", "ok.txt,../y")},
    }
    with reading_remote_clone(str(clone)):
        # pylint: disable-next=protected-access
        ignored = setuptools_clone._Ignored(clone)
        # pylint: disable-next=protected-access
        setuptools_clone._confine_setup_cfg(options, ignored)
    assert options["options.package_data"]["demo"] == ("s", "ok/*")
    assert options["options.data_files"]["share"] == ("s", "ok.txt")
    assert ignored.entries == ["../x", "../y"]


def test_the_clones_setup_cfg_is_finished_as_setuptools_finishes_it(
    clone: Path,
) -> None:
    dist, _said = _apply_cfg(
        clone, _CFG + b"python_requires = >=3.9\n[options.extras_require]\nx = a\n"
    )
    assert dist.metadata.license_files == ["LICENSE"]
    assert str(dist.metadata.python_requires) == ">=3.9"
    assert "x" in dist.metadata.provides_extras


@pytest.mark.parametrize(
    "written",
    ["attr:demo.v", "attr:   demo.v  ", "attr: demo.v"],
    ids=["no-space", "padded", "spaced"],
)
def test_an_attr_version_is_left_out_however_spaced(clone: Path, written: str) -> None:
    """A version Pitloom reads statically is left out unsaid; setuptools
    never imports the module."""
    options = {"metadata": {"version": ("s", written)}}
    with reading_remote_clone(str(clone)):
        # pylint: disable-next=protected-access
        ignored = setuptools_clone._Ignored(clone)
        # pylint: disable-next=protected-access
        setuptools_clone._confine_setup_cfg(options, ignored)
    assert options == {"metadata": {}}
    assert not ignored.code


def test_pyproject_files_and_patterns_out_of_the_clone_are_left_out(
    clone: Path,
) -> None:
    host = _host(clone)
    config: dict[str, Any] = {
        "project": {"license-files": ["LICENSE", ".git/*"]},
        "tool": {
            "setuptools": {
                "packages": ["demo", f"{host}/pkg/hostpkg"],
                "py-modules": [f"{host}/hostmod"],
                "data-files": {"share": ["../x", "ok"]},
                "exclude-package-data": {"demo": ["/etc/*", "*.txt"]},
                "dynamic": {
                    "readme": {"file": [".git/config", "LICENSE"]},
                    "dependencies": {"file": f"{host}/secret.txt"},
                    "optional-dependencies": {"x": {"file": [".git/config"]}},
                },
            }
        },
    }
    with reading_remote_clone(str(clone)):
        # pylint: disable-next=protected-access
        ignored = setuptools_clone._Ignored(clone)
        # pylint: disable-next=protected-access
        setuptools_clone._confine_pyproject(config, ignored)
    tool = config["tool"]["setuptools"]
    assert config["project"]["license-files"] == ["LICENSE"]
    assert (tool["packages"], tool["py-modules"]) == (["demo"], [])
    assert tool["data-files"] == {"share": ["ok"]}
    assert tool["exclude-package-data"] == {"demo": ["*.txt"]}
    assert tool["dynamic"] == {
        "readme": {"file": ["LICENSE"]},
        "dependencies": {"file": []},
        "optional-dependencies": {"x": {"file": []}},
    }
    assert len(ignored.entries) == 8


@pytest.mark.parametrize(
    ("name", "file", "config"),
    [
        ("_apply", "pyproject.toml", _ST),
        ("_finalize_gone", "setup.cfg", _CFG),
    ],
    ids=["apply", "finish"],
)
def test_a_setuptools_without_a_private_piece_fails_the_discovery(
    clone: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    name: str,
    file: str,
    config: bytes,
) -> None:
    """The pieces a clone's configuration is applied with are setuptools'
    own; one gone from setuptools fails the discovery, said, never
    guessed or raised."""
    (clone / file).write_bytes(config)
    if file == "setup.cfg":
        (clone / "setup.py").write_bytes(_SETUP_PY)
        monkeypatch.setattr(
            setuptools_clone, "_FINISHES", ("_finalize_license_files", name)
        )
    else:
        monkeypatch.delattr(pyprojecttoml, name)
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        with reading_remote_clone(str(clone)):
            assert discover(clone) is None
    assert f"Setuptools file discovery failed for '{clone}': setuptools has no " in (
        caplog.text
    )
    assert f".{name}()" in caplog.text
    assert not [r for r in caplog.records if getattr(r, CODE_ATTR, None)]
