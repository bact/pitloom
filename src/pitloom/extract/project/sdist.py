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
:func:`pitloom.core.config.select_project_config` (the rule both share) and
:mod:`pitloom.extract.project._sdist_scan` (the archive pass).
"""

from __future__ import annotations

import dataclasses
import email
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple, TypeVar

from pitloom._toml_io import load_toml_bytes
from pitloom.core import wheel_dist_info
from pitloom.core.config import (
    PitloomConfig,
    parse_pitloom_config,
    pyproject_config_applies,
    select_project_config,
)
from pitloom.core.project import ProjectFile, ProjectMetadata
from pitloom.extract._core_metadata import (
    core_metadata_license_with_source,
    parse_project_urls,
)
from pitloom.extract._extract_utils import field_declared
from pitloom.extract._license import apply_in_package_license
from pitloom.extract._license_detect import license_candidates_from_members
from pitloom.extract.project._pyproject_license import license_from_project_table
from pitloom.extract.project._sdist_scan import (
    CONFIG_MEMBER_MAX_BYTES,
    PKG_INFO,
    PYPROJECT,
    SETUP_CFG,
    scan_archive,
)
from pitloom.extract.project.setuptools_cfg import setup_cfg_pitloom_config
from pitloom.logging_config import field_loss_suffix

log = logging.getLogger(__name__)


def _parse_pkg_info(pkg_info_text: str, source_label: str) -> ProjectMetadata:
    """Parse Metadata-Version 2.x PKG-INFO content into ProjectMetadata."""
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

    author = msg.get("Author")
    if author and author != "UNKNOWN":
        metadata.authors = [{"name": author}]
        metadata.provenance["authors"] = source_label

    requires_dist = msg.get_all("Requires-Dist") or []
    if requires_dist:
        metadata.dependencies = [r.strip() for r in requires_dist]
        metadata.provenance["dependencies"] = source_label

    return metadata


_PYPROJECT_LICENSE_SOURCE = "Source: pyproject.toml | Field: project.license"

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


def _member_bytes(root: dict[str, bytes | None], member: str, sdist_name: str) -> bytes:
    """A present root member's bytes; over the cap is a read failure."""
    raw = root[member]
    if raw is None:
        raise ValueError(
            f"config file {sdist_name}:{member}: "
            f"over {CONFIG_MEMBER_MAX_BYTES} bytes, not read"
        )
    return raw


def _metadata_pyproject(raw: bytes | None, sdist_name: str) -> Any:
    """The root ``pyproject.toml`` parsed for metadata only (no PKG-INFO,
    config not read), or ``None`` with one ``WARNING:`` when it cannot be."""
    try:
        if raw is None:
            raise ValueError(f"over {CONFIG_MEMBER_MAX_BYTES} bytes")
        return load_toml_bytes(raw)
    except ValueError as exc:  # TOMLDecodeError, UnicodeDecodeError
        log.warning(
            "Failed to parse pyproject.toml from sdist member: %s%s",
            f"{sdist_name}: {exc}",
            field_loss_suffix("skipped", *_METADATA_FIELDS),
        )
        return None


def _warn_pkg_info_over_cap(sdist_name: str, *, fallback: bool) -> None:
    """One ``WARNING:`` for a ``PKG-INFO`` header block over
    :data:`~pitloom.core.wheel_dist_info.MAX_METADATA_BYTES` or
    :data:`~pitloom.core.wheel_dist_info.MAX_METADATA_HEADERS`: its fields
    come from the root ``pyproject.toml`` when *fallback*, else stay
    unset."""
    if fallback:
        loss = field_loss_suffix("degraded", *_METADATA_FIELDS)
        loss += field_loss_suffix("skipped", *_PKG_INFO_ONLY_FIELDS)
    else:
        loss = field_loss_suffix("skipped", *_METADATA_FIELDS, *_PKG_INFO_ONLY_FIELDS)
    log.warning(
        "Failed to read PKG-INFO from sdist member: %s: "
        "header block over %d bytes or %d headers%s",
        sdist_name,
        wheel_dist_info.MAX_METADATA_BYTES,
        wheel_dist_info.MAX_METADATA_HEADERS,
        loss,
    )


def _metadata_from_pyproject(data: Any, licence: dict[str, bytes]) -> ProjectMetadata:
    """Fallback ProjectMetadata from a parsed ``pyproject.toml``; its
    licence as a directory reads it, a ``license.file`` from *licence*."""
    proj = data.get("project", {}) if isinstance(data, dict) else {}
    if not isinstance(proj, dict):
        proj = {}
    license_name, license_prov = license_from_project_table(proj, licence.get)
    metadata = ProjectMetadata(
        name=proj.get("name", "unknown"),
        version=proj.get("version"),
        description=proj.get("description"),
        license_name=license_name,
        dependencies=proj.get("dependencies", []),
    )
    if license_prov or field_declared(proj, "license"):
        metadata.provenance["license"] = license_prov or _PYPROJECT_LICENSE_SOURCE
    return metadata


_T = TypeVar("_T")


def _member_config(sdist_name: str, member: str, parse: Callable[[], _T]) -> _T:
    """*parse*, with a failure naming the archive member (as
    :func:`pitloom.core.config_cascade.load_config_file` names a file)."""
    try:
        return parse()
    except ValueError as exc:
        raise ValueError(f"config file {sdist_name}:{member}: {exc}") from exc


def _config(
    root: dict[str, bytes | None], pyproject: Any, sdist_name: str
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
    elif PYPROJECT in members.root and raw_pkg_info is None:
        pyproject = _metadata_pyproject(members.root[PYPROJECT], name)

    if raw_pkg_info is not None:
        metadata = _parse_pkg_info(
            raw_pkg_info.decode("utf-8", errors="replace"),
            f"Source: sdist PKG-INFO | File: {sdist_path.name}",
        )
    elif pyproject is not None:
        metadata = _metadata_from_pyproject(pyproject, members.licence)
    else:
        metadata = ProjectMetadata(name="unknown")
    if raw_pkg_info is None and PKG_INFO in members.root:
        _warn_pkg_info_over_cap(name, fallback=pyproject is not None)
    apply_in_package_license(
        metadata, license_candidates_from_members(members.licence, sdist_path.name)
    )

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
