# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Setuptools' static configuration applied to a ``Distribution``; in a Git
URL's clone, without the settings that would run the repository's own code
(``cmdclass``, an ``attr`` version: setuptools imports the module when it
cannot read the value) or walk the host's directories (a package directory,
a ``packages.find`` folder or a file pattern out of the clone).

An ``attr`` version is always left out in a clone, as the wheel's file list
does not depend on it; the ``WARNING:`` names it only when Pitloom's own
static reader cannot resolve it either, so setuptools would have imported
the module.

See also: :mod:`pitloom.core._models_wheel_setuptools` (the caller),
:mod:`pitloom.core._models_wheel_clone` (the warnings).
"""

from __future__ import annotations

import ntpath
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pitloom.core._models_wheel_clone import (
    clone_root,
    left_out,
    warn_build_code_ignored,
    warn_entries_left_out,
)
from pitloom.core.internal_error import InternalError
from pitloom.core.lfs_pointer import in_remote_clone

if TYPE_CHECKING:
    from setuptools.dist import Distribution

#: What Pitloom's own version reader reads an ``attr`` directive for, as
#: the metadata reader names it (its warnings are said once per name).
_PYPROJECT_VERSION = "pyproject.toml tool.setuptools.dynamic.version"
_SETUP_CFG_VERSION = "setup.cfg metadata.version"


class _Ignored:
    """What a clone's configuration leaves out: the settings that name
    code, and the entries out of the clone."""

    def __init__(self, project_dir: Path) -> None:
        self.project_dir = project_dir
        self.root = clone_root(project_dir)
        self.code: list[str] = []
        self.entries: list[str] = []

    def outside(self, path: str) -> bool:
        """Whether the directory *path* (relative to the project) is out of
        the clone, added to the entries left out when it is."""
        if left_out(os.path.join(self.project_dir, path), self.root):
            self.entries.append(path)
            return True
        return False

    def pattern_outside(self, pattern: str) -> bool:
        """Whether the file pattern *pattern* can reach out of the clone
        (absolute: rooted or with a drive; from the home directory; or with
        a ``..`` part), added to the entries left out when it can."""
        written = pattern.replace("\\", "/")
        if (
            written.startswith(("/", "~"))
            or ntpath.splitdrive(written)[0]
            or ".." in written.split("/")
        ):
            self.entries.append(pattern)
            return True
        return False

    def attr_version(self, attr: str, what: str, setting: str) -> None:
        """Note the ``attr`` version *attr* left out, as code when Pitloom
        cannot read it statically."""
        # Imported here: pitloom.extract imports this package's modules.
        # pylint: disable-next=import-outside-toplevel
        from pitloom.extract.project.setuptools import resolve_attr_directive

        version, _source = resolve_attr_directive(attr, self.project_dir, what)
        if version is None:
            self.code.append(setting)

    def warn(self, file: str) -> None:
        """Say what *file* had left out."""
        warn_build_code_ignored(self.project_dir, file, self.code)
        warn_entries_left_out(self.project_dir, self.entries)


def apply_pyproject(dist: Distribution, path: Path, project_dir: Path) -> None:
    """Apply ``pyproject.toml`` at *path* to *dist*, as setuptools does; in a
    clone, read, left without what :mod:`this module <pitloom.core.
    _models_wheel_setuptools_clone>` leaves out, then expanded and
    applied."""
    # pylint: disable-next=import-outside-toplevel
    from setuptools.config import pyprojecttoml

    if not in_remote_clone():
        pyprojecttoml.apply_configuration(dist, str(path))
        return
    config = pyprojecttoml.read_configuration(str(path), expand=False, dist=dist)
    ignored = _Ignored(project_dir)
    _confine_pyproject(config, ignored)
    ignored.warn("pyproject.toml")
    expanded = pyprojecttoml.expand_configuration(config, str(project_dir), dist=dist)
    _setuptools_apply(pyprojecttoml)(dist, expanded, str(path))


def _setuptools_apply(module: object) -> Any:
    """``apply_configuration()``'s second half, which takes the expanded
    configuration (setuptools 84: ``pyprojecttoml._apply``).

    Raises:
        InternalError: This setuptools has no such function (the discovery
            fails, and says so).
    """
    apply = getattr(module, "_apply", None)
    if not callable(apply):
        raise InternalError("setuptools has no pyprojecttoml._apply()")
    return apply


def _confine_pyproject(config: dict[str, Any], ignored: _Ignored) -> None:
    """Leave out of the validated, unexpanded *config* what *ignored*
    notes."""
    tool = config.get("tool", {}).get("setuptools", {})
    if tool.pop("cmdclass", None):
        ignored.code.append("tool.setuptools.cmdclass")
    dynamic = tool.get("dynamic", {})
    version = dynamic.get("version")
    if isinstance(version, dict) and "attr" in version:
        # Left dynamic and unset: setuptools resolves a dynamic version only
        # from this table, and the wheel's file list does not need it.
        del dynamic["version"]
        ignored.attr_version(
            version["attr"], _PYPROJECT_VERSION, "tool.setuptools.dynamic.version"
        )
    package_dir = tool.get("package-dir")
    if isinstance(package_dir, dict):
        tool["package-dir"] = {
            name: where
            for name, where in package_dir.items()
            if not ignored.outside(where)
        }
    find = tool.get("packages")
    # Validated: a find table's ``where`` is a list; absent, it is ".".
    if isinstance(find, dict) and "where" in find.get("find", {}):
        where = find["find"]["where"]
        find["find"]["where"] = [w for w in where if not ignored.outside(w)]
    for key in ("package-data", "exclude-package-data", "data-files"):
        patterns = tool.get(key)
        if isinstance(patterns, dict):
            tool[key] = {
                name: [p for p in listed if not ignored.pattern_outside(p)]
                for name, listed in patterns.items()
            }


def apply_setup_cfg(dist: Distribution, path: Path, project_dir: Path) -> None:
    """Apply ``setup.cfg`` at *path* to *dist*, as setuptools does; in a
    clone, its options read, left without what :mod:`this module <pitloom.
    core._models_wheel_setuptools_clone>` leaves out, then parsed and
    applied."""
    # pylint: disable-next=import-outside-toplevel
    from setuptools.config import setupcfg

    if not in_remote_clone():
        setupcfg.apply_configuration(dist, str(path))
        return
    # pylint: disable-next=import-outside-toplevel
    from setuptools.dist import Distribution as SetuptoolsDistribution

    # The base class's reading alone: setuptools' own applies them too.
    super(SetuptoolsDistribution, dist).parse_config_files(filenames=[str(path)])
    ignored = _Ignored(project_dir)
    _confine_setup_cfg(dist.command_options, ignored)
    ignored.warn("setup.cfg")
    setupcfg.parse_configuration(dist, dist.command_options)
    # What setupcfg.apply_configuration() ends with (setuptools 84); one
    # gone from a later setuptools fails the discovery, which says so.
    for finish in ("_finalize_license_files", "_finalize_requires"):
        getattr(dist, finish)()


def _confine_setup_cfg(
    options: dict[str, dict[str, tuple[str, str]]], ignored: _Ignored
) -> None:
    """Leave out of the read ``setup.cfg`` *options* what *ignored*
    notes."""
    if options.get("options", {}).pop("cmdclass", None) is not None:
        ignored.code.append("options.cmdclass")
    metadata = options.get("metadata", {})
    _source, version = metadata.get("version", ("", ""))
    if version.startswith("attr:"):
        del metadata["version"]
        ignored.attr_version(
            version[len("attr:") :].strip(), _SETUP_CFG_VERSION, "metadata.version"
        )
    section = options.get("options", {})
    if "package_dir" in section:
        source, value = section["package_dir"]
        kept = [
            line
            for line in _items(value)
            if not ignored.outside(line.partition("=")[2].strip())
        ]
        section["package_dir"] = (source, "\n".join(kept))
    find = options.get("options.packages.find", {})
    if "where" in find:
        source, value = find["where"]
        find["where"] = (
            source,
            "\n".join(w for w in _items(value) if not ignored.outside(w)),
        )
    for name in (
        "options.package_data",
        "options.exclude_package_data",
        "options.data_files",
    ):
        for key, (source, value) in list(options.get(name, {}).items()):
            options[name][key] = (
                source,
                "\n".join(p for p in _items(value) if not ignored.pattern_outside(p)),
            )


def _items(value: str) -> list[str]:
    """The entries of a ``setup.cfg`` list value, as setuptools splits one:
    by line when it spans several, else by comma; blank ones left out."""
    parts = value.splitlines() if "\n" in value else value.split(",")
    return [part.strip() for part in parts if part.strip()]
