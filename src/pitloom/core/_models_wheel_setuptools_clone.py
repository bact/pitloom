# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Setuptools' static configuration applied to a ``Distribution``; in a Git
URL's clone, without the settings that would run the repository's own code
(``cmdclass``, an ``attr`` version: setuptools imports the module when it
cannot read the value), set the ``Distribution`` itself (``setup.cfg``'s
``[global]``: ``src_root``, ``command_packages``) or walk or read the host's
directories or the clone's ``.git`` (a package directory, a package or
module path, a ``packages.find`` folder, a file pattern or a ``file:``
directive out of the clone or in its ``.git``).

An ``attr`` version is always left out in a clone, as the wheel's file list
does not depend on it; the ``WARNING:`` names it only when Pitloom's own
static reader cannot resolve it either, so setuptools would have imported
the module. Of ``setup.cfg`` only ``[metadata]``, ``[options]`` and the
``[options.*]`` sections are applied in a clone; a command's section
(``[egg_info]``, ``[build_py]``) configures a command the discovery runs
with Pitloom's own settings.

The clone's path reads setuptools' private pieces (``pyprojecttoml._apply``,
``Distribution._finalize_license_files``, ``_finalize_requires``): a later
setuptools without one fails the discovery with an
:class:`~pitloom.core.internal_error.InternalError` that the ``WARNING:``
names, and the file list falls back.

See also: :mod:`pitloom.core._models_wheel_setuptools` (the caller),
:mod:`pitloom.core._models_wheel_clone` (the warnings).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from pitloom.core._models_wheel_clone import LeftOut
from pitloom.core.clone_mark import in_remote_clone
from pitloom.core.internal_error import InternalError

if TYPE_CHECKING:
    from setuptools.dist import Distribution

#: What Pitloom's own version reader reads an ``attr`` directive for, as
#: the metadata reader names it (its warnings are said once per name).
_PYPROJECT_VERSION = "pyproject.toml tool.setuptools.dynamic.version"
_SETUP_CFG_VERSION = "setup.cfg metadata.version"
#: The setting a ``setup.cfg`` ``[global]`` section is named as: the whole
#: section, as a dotted setting names its table.
_GLOBAL = "global"
#: What ``setup.cfg`` writes before the files a value is read from.
_FILE_DIRECTIVE = "file:"
#: ``Distribution`` methods ``setupcfg.apply_configuration()`` ends with
#: (setuptools 84).
_FINISHES = ("_finalize_license_files", "_finalize_requires")


class _Ignored(LeftOut):
    """What a clone's configuration leaves out
    (:class:`~pitloom.core._models_wheel_clone.LeftOut`), and an ``attr``
    version."""

    def attr_version(self, attr: str, what: str, setting: str) -> None:
        """Note the ``attr`` version *attr* left out, as code when Pitloom
        cannot read it statically."""
        # Imported here: pitloom.extract imports this package's modules.
        # pylint: disable-next=import-outside-toplevel
        from pitloom.extract.project.setuptools import resolve_attr_directive

        version, _source = resolve_attr_directive(attr, self.project_dir, what)
        if version is None:
            self.code.append(setting)


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
    apply = _private(pyprojecttoml, "_apply", "pyprojecttoml")
    config = pyprojecttoml.read_configuration(str(path), expand=False, dist=dist)
    ignored = _Ignored(project_dir)
    _confine_pyproject(config, ignored)
    ignored.warn("pyproject.toml")
    expanded = pyprojecttoml.expand_configuration(config, str(project_dir), dist=dist)
    apply(dist, expanded, str(path))


def _private(owner: object, name: str, shown: str) -> Any:
    """The private setuptools function *name* of *owner* (named *shown*)
    the clone's path calls.

    Raises:
        InternalError: This setuptools has no such function (the discovery
            fails, and says so).
    """
    found = getattr(owner, name, None)
    if not callable(found):
        raise InternalError(f"setuptools has no {shown}.{name}()")
    return found


def _confine_pyproject(config: dict[str, Any], ignored: _Ignored) -> None:
    """Leave out of the validated, unexpanded *config* what *ignored*
    notes."""
    tool = config.get("tool", {}).get("setuptools", {})
    if tool.pop("cmdclass", None):
        ignored.code.append("tool.setuptools.cmdclass")
    _confine_dynamic(tool.get("dynamic", {}), ignored)
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
        find["find"]["where"] = ignored.kept(find["find"]["where"], ignored.outside)
    for table, key in (
        (tool, "packages"),
        (tool, "py-modules"),
        (tool, "license-files"),
        (config.get("project", {}), "license-files"),
    ):
        if isinstance(table.get(key), list):
            table[key] = ignored.kept(table[key], ignored.pattern_outside)
    for key in ("package-data", "exclude-package-data", "data-files"):
        patterns = tool.get(key)
        if isinstance(patterns, dict):
            tool[key] = {
                name: ignored.kept(listed, ignored.pattern_outside)
                for name, listed in patterns.items()
            }


def _confine_dynamic(dynamic: dict[str, Any], ignored: _Ignored) -> None:
    """Leave out of ``[tool.setuptools.dynamic]`` an ``attr`` version and
    each file out of the clone or in its ``.git`` (an empty list reads
    nothing)."""
    version = dynamic.get("version")
    if isinstance(version, dict) and "attr" in version:
        # Left dynamic and unset: setuptools resolves a dynamic version only
        # from this table, and the wheel's file list does not need it.
        del dynamic["version"]
        ignored.attr_version(
            version["attr"], _PYPROJECT_VERSION, "tool.setuptools.dynamic.version"
        )
    extras = dynamic.get("optional-dependencies")
    directives = [*dynamic.values(), *(extras.values() if extras else ())]
    for directive in directives:
        if isinstance(directive, dict) and "file" in directive:
            files = directive["file"]
            listed = [files] if isinstance(files, str) else list(files)
            directive["file"] = ignored.kept(listed, ignored.outside)


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

    finishes = [_private(dist, name, "Distribution") for name in _FINISHES]
    before = dict(vars(dist))
    # The base class's reading alone: setuptools' own applies them too.
    super(SetuptoolsDistribution, dist).parse_config_files(filenames=[str(path)])
    ignored = _Ignored(project_dir)
    if _GLOBAL in dist.command_options:
        ignored.code.append(_GLOBAL)
    _restore(dist, before)
    _confine_setup_cfg(dist.command_options, ignored)
    ignored.warn("setup.cfg")
    setupcfg.parse_configuration(dist, dist.command_options)
    for finish in finishes:
        finish()


def _restore(dist: Distribution, before: dict[str, Any]) -> None:
    """*dist*'s attributes as *before* holds them: what a ``[global]``
    section set on it (``src_root``, ``command_packages``) is undone."""
    for name in set(vars(dist)) - set(before):
        delattr(dist, name)
    for name, value in before.items():
        if getattr(dist, name) is not value:
            setattr(dist, name, value)


def _confine_setup_cfg(
    options: dict[str, dict[str, tuple[str, str]]], ignored: _Ignored
) -> None:
    """Leave out of the read ``setup.cfg`` *options* what *ignored*
    notes, and every section but ``[metadata]``, ``[options]`` and
    ``[options.*]``."""
    for name in list(options):
        if name not in ("metadata", "options") and not name.startswith("options."):
            del options[name]
    if options.get("options", {}).pop("cmdclass", None) is not None:
        ignored.code.append("options.cmdclass")
    metadata = options.get("metadata", {})
    _source, version = metadata.get("version", ("", ""))
    if version.startswith("attr:"):
        del metadata["version"]
        ignored.attr_version(
            version[len("attr:") :].strip(), _SETUP_CFG_VERSION, "metadata.version"
        )
    _confine_cfg_paths(options, ignored)
    for section in options.values():
        for key, (source, value) in list(section.items()):
            if value.strip().startswith(_FILE_DIRECTIVE):
                spec = value.strip()[len(_FILE_DIRECTIVE) :]
                files = [part.strip() for part in spec.split(",") if part.strip()]
                kept = ignored.kept(files, ignored.outside)
                # A value of no file left is unset: setuptools would warn of
                # the folder itself as a file it cannot find.
                if kept:
                    section[key] = (source, f"{_FILE_DIRECTIVE} {', '.join(kept)}")
                else:
                    del section[key]


def _confine_cfg_paths(
    options: dict[str, dict[str, tuple[str, str]]], ignored: _Ignored
) -> None:
    """Leave out of the read ``setup.cfg`` *options* the folders, package
    and module paths and file patterns out of the clone."""
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
            "\n".join(ignored.kept(_items(value), ignored.outside)),
        )
    patterns = [
        (options.get(name, {}), key)
        for name in (
            "options.package_data",
            "options.exclude_package_data",
            "options.data_files",
        )
        for key in options.get(name, {})
    ]
    patterns += [(section, "packages"), (section, "py_modules")]
    metadata = options.get("metadata", {})
    patterns += [(metadata, "license_files"), (metadata, "license_file")]
    for table, key in patterns:
        # ``find:`` reads as a name, never as a path out of the clone.
        if key in table:
            source, value = table[key]
            kept = ignored.kept(_items(value), ignored.pattern_outside)
            table[key] = (source, "\n".join(kept))


def _items(value: str) -> list[str]:
    """The entries of a ``setup.cfg`` list value, as setuptools splits one:
    by line when it spans several, else by comma; blank ones left out."""
    parts = value.splitlines() if "\n" in value else value.split(",")
    return [part.strip() for part in parts if part.strip()]
