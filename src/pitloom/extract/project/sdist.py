# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Extractor for an sdist archive: project metadata (``PKG-INFO``, falling
back to ``pyproject.toml``) and the project's own Pitloom config (the root
``pyproject.toml``'s ``[tool.pitloom]``, else ``setup.cfg``'s
``[tool:pitloom]``), read as for the unpacked project directory.

See also: :mod:`pitloom.extract.project.reader` (the directory counterpart)
and :func:`pitloom.core.config.select_project_config` (the rule both share).
"""

from __future__ import annotations

import dataclasses
import email
import functools
import hashlib
import logging
import tarfile
import zipfile
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import IO, Any, NamedTuple, TypeVar

from pitloom._toml_io import load_toml_bytes
from pitloom.core.archive_member_names import file_members, zip_file_members
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


#: Root members read whole: metadata and the project's own config.
_PKG_INFO = "PKG-INFO"
_PYPROJECT = "pyproject.toml"
_SETUP_CFG = "setup.cfg"
_ROOT_MEMBERS = (_PKG_INFO, _PYPROJECT, _SETUP_CFG)

#: Largest ``pyproject.toml``/``setup.cfg`` member read into memory. Real
#: ones are a few KiB; a larger one is a read failure, as invalid TOML is.
CONFIG_MEMBER_MAX_BYTES = 1024 * 1024

_METADATA_FIELDS = ("name", "version", "description", "dependencies")


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


class _Members(NamedTuple):
    """Root members read whole (by basename), and every file's entry. A
    root member over :data:`CONFIG_MEMBER_MAX_BYTES` maps to ``None``."""

    root: dict[str, bytes | None]
    files: list[ProjectFile]


def _read_member(name: str, stream: IO[bytes], keep: bool) -> tuple[bytes | None, str]:
    """Hash *stream* in chunks; return its bytes too when *keep* (``None``
    past :data:`CONFIG_MEMBER_MAX_BYTES` for a config member)."""
    hasher = hashlib.sha256()
    kept: bytearray | None = bytearray() if keep else None
    limit = None if Path(name).name == _PKG_INFO else CONFIG_MEMBER_MAX_BYTES
    with stream:
        while chunk := stream.read(8192):
            hasher.update(chunk)
            if kept is None:
                continue
            kept += chunk
            if limit is not None and len(kept) > limit:
                kept = None
    return (bytes(kept) if kept is not None else None), hasher.hexdigest()


#: One archive file: (install-location name, raw archive name, opener).
_Entry = tuple[str, str, Callable[[], IO[bytes] | None]]


def _scan(
    entries: Iterator[_Entry],
    *,
    root_only: bool = False,
) -> _Members:
    """Hash every member; keep the first root-level member of each
    :data:`_ROOT_MEMBERS` basename, archive order deciding a tie between
    two top-level directories. Repeats of one name never get here:
    :func:`~pitloom.core.archive_member_names.file_members` keeps the
    last, as unpacking leaves it. With *root_only*, open only those members
    and list no files. Files come in archive order; :func:`read_sdist`
    sorts them. A file's ``physical_path`` is its raw archive name,
    so a registry keyed by it before names were normalised still hits."""
    root: dict[str, bytes | None] = {}
    files: list[ProjectFile] = []
    for name, raw, open_member in entries:
        parts = Path(name).parts
        wanted = len(parts) == 2 and parts[1] in _ROOT_MEMBERS and parts[1] not in root
        if root_only and not wanted:
            continue
        stream = open_member()
        if stream is None:
            continue
        content, digest = _read_member(name, stream, wanted)
        if wanted:
            root[parts[1]] = content
        if not root_only:
            files.append(
                ProjectFile(
                    physical_path=raw, distribution_path=name, digest_sha256=digest
                )
            )
    return _Members(root, files)


def _tar_entries(
    tf: tarfile.TarFile, logger: logging.Logger | None, archive_name: str
) -> Iterator[_Entry]:
    files = ((m.name, m.size, m) for m in tf.getmembers() if m.isfile())
    for name, member in file_members(files, archive_name, logger, dot_prefix_ok=True):
        yield name, member.name, functools.partial(tf.extractfile, member)


def _zip_entries(
    zf: zipfile.ZipFile, logger: logging.Logger | None, archive_name: str
) -> Iterator[_Entry]:
    for name, info in zip_file_members(zf, archive_name, logger):
        yield name, info.orig_filename, functools.partial(zf.open, info)


def _scan_archive(sdist_path: Path, *, root_only: bool = False) -> _Members:
    """Scan the archive's members under their normalised names. Member-name
    warnings come from the full scan only: a *root_only* read serves
    ``--verbose`` source reporting, whose run reads the archive in full."""
    logger = None if root_only else log
    if sdist_path.name.lower().endswith(".zip"):
        with zipfile.ZipFile(sdist_path, "r") as zf:
            entries = _zip_entries(zf, logger, sdist_path.name)
            return _scan(entries, root_only=root_only)
    with tarfile.open(sdist_path, "r:*") as tf:
        entries = _tar_entries(tf, logger, sdist_path.name)
        return _scan(entries, root_only=root_only)


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


def _metadata_from_pyproject(data: Any) -> ProjectMetadata:
    """Fallback ProjectMetadata from a parsed ``pyproject.toml``."""
    proj = data.get("project", {}) if isinstance(data, dict) else {}
    if not isinstance(proj, dict):
        proj = {}
    return ProjectMetadata(
        name=proj.get("name", "unknown"),
        version=proj.get("version"),
        description=proj.get("description"),
        dependencies=proj.get("dependencies", []),
    )


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
            sdist_name, _PYPROJECT, lambda: parse_pitloom_config(pyproject)
        )
    )

    def read_setup_cfg() -> PitloomConfig:
        raw = _member_bytes(root, _SETUP_CFG, sdist_name)
        return _member_config(
            sdist_name,
            _SETUP_CFG,
            lambda: setup_cfg_pitloom_config(raw.decode("utf-8")),
        )

    config, member = select_project_config(
        pyproject_config,
        pyproject_config_applies(pyproject),
        read_setup_cfg if _SETUP_CFG in root else None,
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
    members = _scan_archive(sdist_path)
    raw_pkg_info = members.root.get(_PKG_INFO)
    pyproject: Any = None
    if _PYPROJECT in members.root and read_config:
        raw = _member_bytes(members.root, _PYPROJECT, name)
        pyproject = _member_config(name, _PYPROJECT, lambda: load_toml_bytes(raw))
    elif _PYPROJECT in members.root and raw_pkg_info is None:
        pyproject = _metadata_pyproject(members.root[_PYPROJECT], name)

    if raw_pkg_info is not None:
        metadata = _parse_pkg_info(
            raw_pkg_info.decode("utf-8", errors="replace"),
            f"Source: sdist PKG-INFO | File: {sdist_path.name}",
        )
    elif pyproject is not None:
        metadata = _metadata_from_pyproject(pyproject)
    else:
        metadata = ProjectMetadata(name="unknown")

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
    root = _scan_archive(sdist_path, root_only=True).root
    pyproject: Any = None
    if _PYPROJECT in root:
        raw = _member_bytes(root, _PYPROJECT, str(sdist_path))
        pyproject = _member_config(
            str(sdist_path), _PYPROJECT, lambda: load_toml_bytes(raw)
        )
    _, member = _config(root, pyproject, str(sdist_path))
    tool = pyproject.get("tool") if isinstance(pyproject, dict) else None
    table = tool.get("pitloom") if isinstance(tool, dict) else None
    if member != _PYPROJECT or not isinstance(table, dict):
        return member, {}
    return member, table
