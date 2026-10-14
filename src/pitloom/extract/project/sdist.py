# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Extractor for an sdist archive: project metadata (``PKG-INFO``, falling
back to ``pyproject.toml``), the licence its own licence files state, and
the project's own Pitloom config (the root ``pyproject.toml``'s
``[tool.pitloom]``, else ``setup.cfg``'s ``[tool:pitloom]``), read as for
the unpacked project directory.

See also: :mod:`pitloom.extract.project.reader` (the directory counterpart),
:func:`pitloom.core.config.select_project_config` (the rule both share),
:mod:`pitloom.extract.project._sdist_scan` (the archive pass) and
:mod:`pitloom.extract.project._sdist_pyproject` (the fallback).
"""

from __future__ import annotations

import dataclasses
import email
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple, TypeVar

from pitloom._toml_io import load_toml_bytes
from pitloom.core.config import (
    PitloomConfig,
    parse_pitloom_config,
    pyproject_config_applies,
    select_project_config,
)
from pitloom.core.project import ProjectFile, ProjectMetadata
from pitloom.extract._core_metadata import (
    core_metadata_license_with_source,
    parse_core_metadata_authors,
    parse_project_urls,
)
from pitloom.extract._license import apply_in_package_license_files
from pitloom.extract.authors import collapse_whitespace, warn_project_authors_unread
from pitloom.extract.project._sdist_pyproject import metadata_from_pyproject
from pitloom.extract.project._sdist_scan import (
    PKG_INFO,
    PYPROJECT,
    SETUP_CFG,
    scan_archive,
)
from pitloom.extract.project.poetry import (
    POETRY_AUTHORS_SOURCE,
    parse_poetry_authors,
)
from pitloom.extract.project.setuptools_cfg import setup_cfg_pitloom_config
from pitloom.logging_config import Cap, field_loss_suffix, warn_over_cap

log = logging.getLogger(__name__)


def _parse_pkg_info(
    pkg_info_text: str, source_label: str, *, quiet_authors: bool = False
) -> ProjectMetadata:
    """Parse Metadata-Version 2.x PKG-INFO content into ProjectMetadata.

    *quiet_authors* silences every author ``WARNING:`` (a split, a cap, an
    address) when the archive's ``pyproject.toml`` declares the authors,
    which then replace these: a discarded read."""
    msg = email.message_from_string(pkg_info_text)
    name = msg.get("Name", "unknown")
    version = msg.get("Version")
    summary = msg.get("Summary")
    license_name, license_source = core_metadata_license_with_source(msg, source_label)
    license_name = license_name or None
    requires_python = msg.get("Requires-Python")

    metadata = ProjectMetadata(
        name=name,
        version=version,
        description=summary,
        license_name=license_name,
        requires_python=requires_python,
    )
    metadata.provenance["name"] = source_label
    # Unlike Poetry's `python = "*"` or setup.cfg's `python_requires =`,
    # PKG-INFO/Core-Metadata has no convention where an empty header value
    # means "explicitly no constraint" rather than just missing data, so
    # truthy-gating these below is not the same presence-vs-truthy bug
    # fixed elsewhere -- see AGENTS.md's "tri-state signal" bullet.
    if version:
        metadata.provenance["version"] = source_label
    if summary:
        metadata.provenance["description"] = source_label
    if license_name:
        metadata.provenance["license"] = license_source
    if requires_python:
        metadata.provenance["requires_python"] = source_label

    urls = parse_project_urls(msg, include_homepage=False)
    if urls:
        metadata.urls = urls
        metadata.provenance["urls"] = source_label

    authors = parse_core_metadata_authors(msg, quiet=quiet_authors)
    if authors:
        metadata.authors = authors
        metadata.provenance["authors"] = source_label

    requires_dist = msg.get_all("Requires-Dist") or []
    if requires_dist:
        metadata.dependencies = [r.strip() for r in requires_dist]
        metadata.provenance["dependencies"] = source_label

    return metadata


_PYPROJECT_AUTHORS_SOURCE = "Source: pyproject.toml | Field: project.authors"

_METADATA_FIELDS = ("name", "version", "description", "dependencies")
#: What :func:`_parse_pkg_info` reads beyond :data:`_METADATA_FIELDS`.
_PKG_INFO_ONLY_FIELDS = ("license", "requires_python", "urls", "authors")


class SdistContents(NamedTuple):
    """What :func:`read_sdist` found in an archive."""

    metadata: ProjectMetadata
    files: list[ProjectFile]
    #: The project's own config; the defaults when it has none (or when
    #: :func:`read_sdist` was told not to read it).
    config: PitloomConfig
    #: The member the config came from (``"pyproject.toml"``/
    #: ``"setup.cfg"``), or ``None``.
    config_member: str | None


def _member_bytes(root: dict[str, bytes | Cap], member: str, sdist_name: str) -> bytes:
    """A present root member's bytes; over the cap is a read failure."""
    raw = root[member]
    if isinstance(raw, Cap):
        raise ValueError(f"config file {sdist_name}:{member}: {raw.reason}; not read")
    return raw


def _metadata_pyproject(raw: bytes | Cap, sdist_name: str) -> Any:
    """The root ``pyproject.toml`` parsed for metadata only (no PKG-INFO,
    config not read), or ``None`` with one ``WARNING:`` when it cannot be."""
    skipped = field_loss_suffix("skipped", *_METADATA_FIELDS)
    if isinstance(raw, Cap):
        warn_over_cap(log, raw, f"{sdist_name}:{PYPROJECT}", f"not read{skipped}")
        return None
    try:
        return load_toml_bytes(raw)
    except ValueError as exc:  # TOMLDecodeError, UnicodeDecodeError
        log.warning(
            "Failed to parse pyproject.toml from sdist member: %s%s",
            f"{sdist_name}: {exc}",
            skipped,
        )
        return None


def _warn_pkg_info_over_cap(sdist_name: str, cap: Cap, *, fallback: bool) -> None:
    """One ``WARNING:`` for a ``PKG-INFO`` header block over *cap*
    (:data:`~pitloom.core.wheel_dist_info.MAX_METADATA_BYTES` or
    :data:`~pitloom.core.wheel_dist_info.MAX_METADATA_HEADERS`): its fields
    come from the root ``pyproject.toml`` when *fallback*, else stay
    unset."""
    if fallback:
        loss = field_loss_suffix("degraded", *_METADATA_FIELDS)
        loss += field_loss_suffix("skipped", *_PKG_INFO_ONLY_FIELDS)
    else:
        loss = field_loss_suffix("skipped", *_METADATA_FIELDS, *_PKG_INFO_ONLY_FIELDS)
    warn_over_cap(log, cap, f"{sdist_name}:{PKG_INFO}", f"not read{loss}")


class _DeclaredAuthors(NamedTuple):
    """The authors a ``pyproject.toml`` declares, and their provenance."""

    authors: list[dict[str, str]]
    source: str


def _poetry_authors(pyproject: Any) -> _DeclaredAuthors | None:
    """``[tool.poetry].authors`` (``"Name <email>"`` strings, never split)
    as the directory reads them, or ``None`` when not a list of strings."""
    tool = pyproject.get("tool") if isinstance(pyproject, dict) else None
    poetry = tool.get("poetry") if isinstance(tool, dict) else None
    declared = poetry.get("authors") if isinstance(poetry, dict) else None
    if not isinstance(declared, list) or not all(
        isinstance(entry, str) for entry in declared
    ):
        return None
    return _DeclaredAuthors(parse_poetry_authors(declared), POETRY_AUTHORS_SOURCE)


def _declared_authors(pyproject: Any) -> _DeclaredAuthors | None:
    """``[project].authors`` of a parsed ``pyproject.toml`` as
    ``{name?, email?}`` dicts in declared order (a name's white space
    collapsed, :func:`~pitloom.extract.authors.collapse_whitespace`), else,
    as the directory fills that gap, ``[tool.poetry].authors``
    (:func:`_poetry_authors`);
    ``None`` when neither is declared as a list of tables with string
    values or of strings (``PKG-INFO`` then stays the source)."""
    proj = pyproject.get("project") if isinstance(pyproject, dict) else None
    declared = proj.get("authors") if isinstance(proj, dict) else None
    if declared is None:
        return _poetry_authors(pyproject)
    if not isinstance(declared, list):
        return None
    authors: list[dict[str, str]] = []
    for entry in declared:
        if not isinstance(entry, dict) or not all(
            isinstance(entry.get(key, ""), str) for key in ("name", "email")
        ):
            return None
        named = {**entry, "name": collapse_whitespace(entry.get("name", ""))}
        author = {key: named[key] for key in ("name", "email") if named.get(key)}
        if author:
            authors.append(author)
    return _DeclaredAuthors(authors, _PYPROJECT_AUTHORS_SOURCE)


def _apply_declared_authors(
    metadata: ProjectMetadata, declared: _DeclaredAuthors | None
) -> None:
    """Take *metadata*'s authors from the archive's ``pyproject.toml``
    (*declared*, :func:`_declared_authors`) when it declares them:
    ``PKG-INFO`` lists authors with an address before the others, the
    declared order is only in ``pyproject.toml`` (see
    :func:`~pitloom.extract.authors.author_pairs`)."""
    if declared is None:
        return
    metadata.authors = declared.authors
    metadata.provenance["authors"] = declared.source


def _optional_pyproject(raw: bytes | Cap, sdist_name: str) -> Any:
    """The root ``pyproject.toml`` parsed only for the declared authors, or
    ``None`` with one ``WARNING:`` when it cannot be: the authors then come
    from ``PKG-INFO``, without their declared order, name-only authors
    joined into one ``Author`` field read as one."""
    where = f"{sdist_name}:{PYPROJECT}"
    if isinstance(raw, Cap):
        outcome = f"project metadata not read, authors from the {PKG_INFO}"
        warn_over_cap(log, raw, where, outcome)
        return None
    try:
        return load_toml_bytes(raw)
    except ValueError as exc:  # TOMLDecodeError, UnicodeDecodeError
        warn_project_authors_unread(where, exc, PKG_INFO)
        return None


_T = TypeVar("_T")


def _member_config(sdist_name: str, member: str, parse: Callable[[], _T]) -> _T:
    """*parse*, with a failure naming the archive member (as
    :func:`pitloom.core.config_cascade.load_config_file` names a file)."""
    try:
        return parse()
    except ValueError as exc:
        raise ValueError(f"config file {sdist_name}:{member}: {exc}") from exc


def _config(
    root: dict[str, bytes | Cap], pyproject: Any, sdist_name: str
) -> tuple[PitloomConfig, str | None]:
    """The archive's own config and the member it came from, chosen by the
    rule a directory uses (:func:`~pitloom.core.config.select_project_config`).
    *pyproject* is the parsed root ``pyproject.toml``, ``None`` when absent."""
    pyproject_config = (
        None
        if pyproject is None
        else _member_config(
            sdist_name,
            PYPROJECT,
            lambda: parse_pitloom_config(pyproject, source=f"{sdist_name}:{PYPROJECT}"),
        )
    )

    def read_setup_cfg() -> PitloomConfig:
        raw = _member_bytes(root, SETUP_CFG, sdist_name)
        return _member_config(
            sdist_name,
            SETUP_CFG,
            lambda: setup_cfg_pitloom_config(
                raw.decode("utf-8"), f"{sdist_name}:{SETUP_CFG}"
            ),
        )

    config, member = select_project_config(
        pyproject_config,
        pyproject_config_applies(pyproject),
        read_setup_cfg if SETUP_CFG in root else None,
    )
    # Neither can apply to an archive: an id-registry names a file inside it,
    # and fragments merge only into a directory's SBOM. Dropped here, so
    # every surface given this config ignores them (documented, not warned).
    return dataclasses.replace(config, id_registry=None, fragments=[]), member


def read_sdist(sdist_path: Path, *, read_config: bool = True) -> SdistContents:
    """Read metadata, files and the project's own config from an sdist
    archive (.tar.gz, .tgz, .zip).

    The config is read as for the unpacked directory: the root
    ``pyproject.toml``'s ``[tool.pitloom]``, else ``setup.cfg``'s
    ``[tool:pitloom]`` (:func:`~pitloom.core.config.select_project_config`),
    minus ``id-registry`` and fragments, which cannot apply to an archive.
    Without *read_config* it is not parsed and the defaults are returned --
    an explicit config replaces it, so a fault in it cannot fail the read.

    Raises:
        FileNotFoundError: *sdist_path* does not exist.
        ValueError: with *read_config*, the archive's own config cannot be
            read (invalid TOML, not UTF-8, over the size cap) or is invalid,
            as for a directory; the message names the member
            (``<archive>:pyproject.toml``).
    """
    if not sdist_path.exists():
        raise FileNotFoundError(f"Sdist archive not found: {sdist_path}")

    # The archive as given, as load_config_file() names a --config file.
    name = str(sdist_path)
    members = scan_archive(sdist_path)
    raw_pkg_info = members.root.get(PKG_INFO)
    pyproject: Any = None
    if PYPROJECT in members.root and read_config:
        raw = _member_bytes(members.root, PYPROJECT, name)
        pyproject = _member_config(name, PYPROJECT, lambda: load_toml_bytes(raw))
    elif PYPROJECT in members.root and not isinstance(raw_pkg_info, bytes):
        pyproject = _metadata_pyproject(members.root[PYPROJECT], name)
    elif PYPROJECT in members.root:
        pyproject = _optional_pyproject(members.root[PYPROJECT], name)

    declared_authors = _declared_authors(pyproject)
    if isinstance(raw_pkg_info, bytes):
        metadata = _parse_pkg_info(
            raw_pkg_info.decode("utf-8", errors="replace"),
            f"Source: sdist PKG-INFO | File: {sdist_path.name}",
            quiet_authors=declared_authors is not None,
        )
    elif pyproject is not None:
        metadata = metadata_from_pyproject(pyproject, members.licence, name)
    else:
        metadata = ProjectMetadata(name="unknown")
    _apply_declared_authors(metadata, declared_authors)
    if isinstance(raw_pkg_info, Cap):
        _warn_pkg_info_over_cap(name, raw_pkg_info, fallback=pyproject is not None)
    apply_in_package_license_files(metadata, members.licence, sdist_path.name)

    config, member = (
        _config(members.root, pyproject, name)
        if read_config
        else (PitloomConfig(), None)
    )
    # Archive order is the writer's; SPDX ids are minted in file order.
    members.files.sort(key=lambda f: f.distribution_path)
    return SdistContents(metadata, members.files, config, member)


def sdist_config_source(sdist_path: Path) -> tuple[str | None, dict[str, Any]]:
    """For ``--verbose``: the member an sdist's own config comes from (see
    :attr:`SdistContents.config_member`), and its raw ``[tool.pitloom]``
    table when that member is ``pyproject.toml`` (``{}`` otherwise, as for a
    directory's ``setup.cfg``). Reads only the root members.

    Raises:
        ValueError: as :func:`read_sdist` does for an invalid config.
    """
    root = scan_archive(sdist_path, root_only=True).root
    pyproject: Any = None
    if PYPROJECT in root:
        raw = _member_bytes(root, PYPROJECT, str(sdist_path))
        pyproject = _member_config(
            str(sdist_path), PYPROJECT, lambda: load_toml_bytes(raw)
        )
    _, member = _config(root, pyproject, str(sdist_path))
    tool = pyproject.get("tool") if isinstance(pyproject, dict) else None
    table = tool.get("pitloom") if isinstance(tool, dict) else None
    if member != PYPROJECT or not isinstance(table, dict):
        return member, {}
    return member, table
