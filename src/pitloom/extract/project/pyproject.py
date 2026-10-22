# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Extractor for Python project metadata from pyproject.toml.

Supports ``[project]`` (PEP 517/518/621) and ``[tool.poetry]`` sections.
When both are present, ``[project]`` values take precedence and
``[tool.poetry]`` fills any gaps.

See also: :mod:`pitloom.extract.project.pyproject_dynamic` for PEP 621
``dynamic`` field resolution (``prepare_dynamic_version()``, called from
:func:`read_pyproject` below), and
:mod:`pitloom.extract.project._pyproject_license` for ``project.license``
and the licence classifiers, and
:mod:`pitloom.extract.project._pyproject_fields` for the ``[project]``
fields read from :class:`pyproject_metadata.StandardMetadata`.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pyproject_metadata import ConfigurationError, StandardMetadata

from pitloom._toml_io import load_toml_file
from pitloom.core.config import PitloomConfig, parse_pitloom_config
from pitloom.core.project import ProjectMetadata, merge_project_metadata
from pitloom.core.requirements import normalize_dependency_specifier
from pitloom.extract._core_metadata import license_from_classifiers
from pitloom.extract._extract_utils import field_declared, quote_source
from pitloom.extract._license import (
    apply_in_package_license_files,
    classify_license,
)
from pitloom.extract._license_detect import read_license_members
from pitloom.extract.lock.common import POETRY_LOCK_SOURCE_NAME
from pitloom.extract.lock.poetry import extract_poetry_lock_dependencies
from pitloom.extract.lock.poetry_hash import extract_poetry_lock_hashes
from pitloom.extract.project._poetry_extras import (
    defer_to_poetry_lists,
    poetry_backend_reads,
    warn_unread_poetry_fields,
)
from pitloom.extract.project._poetry_fields import read_poetry_section
from pitloom.extract.project._pyproject_deep import hold_deep_requirements
from pitloom.extract.project._pyproject_fields import (
    build_provenance,
    confine_readme_file,
    extract_authors,
    extract_readme,
    strip_missing_readme,
)
from pitloom.extract.project._pyproject_license import (
    confine_license_file,
    stated_pyproject_license,
)
from pitloom.extract.project._setuptools_dynamic import read_setuptools_dynamic
from pitloom.extract.project.poetry import extract_poetry_metadata
from pitloom.extract.project.pyproject_dynamic import prepare_dynamic_version

log = logging.getLogger(__name__)


def _read_pyproject_fallback(
    data: dict[str, Any],
    pyproject_path: Path,
    name: str,
    pitloom_config: PitloomConfig,
    *,
    include_locked_dependencies: bool,
    quiet: bool = False,
) -> tuple[ProjectMetadata, PitloomConfig]:
    """Handle fallback when [project] section is absent or missing a name."""
    poetry_meta = _try_read_poetry(
        data,
        pyproject_path.parent,
        include_locked_dependencies=include_locked_dependencies,
        quiet=quiet,
    )
    if poetry_meta is not None:
        return poetry_meta, pitloom_config
    prov: dict[str, str] = {}
    if name:
        prov["name"] = "Source: pyproject.toml | Field: project.name"
    metadata = ProjectMetadata(name=name, provenance=prov)
    apply_in_package_license_files(
        metadata, read_license_members(pyproject_path.parent)
    )
    return metadata, pitloom_config


def _is_license_classifier_conflict(exc: ConfigurationError) -> bool:
    """Whether *exc* is pyproject-metadata's "SPDX license expression is
    not compatible with 'License ::' classifiers" validation error --
    the one specific, narrow case :func:`read_pyproject` relaxes, not a
    stand-in for treating arbitrary ``project.license`` errors as
    recoverable.

    pyproject-metadata raises ``ConfigurationError`` with
    ``key == "project.license"`` for *two* distinct validation failures
    (this classifier conflict, and a separate pre-2.4-metadata-version
    SPDX-string error) -- ``.key`` alone can't tell them apart, so this
    also matches the full distinguishing phrase from the classifier-
    conflict message specifically. pyproject-metadata exposes no more
    stable discriminator than message text for this, so a reworded message
    stops matching."""
    return (
        exc.key == "project.license"
        and "not compatible with 'License ::' classifiers" in str(exc)
    )


def _drop_placeholder_license(data: dict[str, Any]) -> dict[str, Any] | None:
    """*data* without ``project.license`` when that is only an
    ``UNKNOWN``/``NOASSERTION`` placeholder, else ``None``. The placeholder
    is weak, so the ``License ::`` classifier it conflicts with wins anyway
    (:func:`~pitloom.extract._core_metadata.license_or_classifier`): it is
    the classifiers that carry the licence, never redundant."""
    project_data: dict[str, Any] = data.get("project", {})
    license_value = project_data.get("license")
    classified = (
        classify_license(license_value, warn=False)
        if isinstance(license_value, str)
        else None
    )
    if classified is None or classified.kind != "noassertion":
        return None
    kept = {k: v for k, v in project_data.items() if k != "license"}
    return {**data, "project": kept}


def _drop_redundant_license_classifiers(data: dict[str, Any]) -> dict[str, Any]:
    """Strip ``License ::`` trove classifiers from a parsed
    ``pyproject.toml`` mapping, leaving every other classifier and
    ``[project]`` field untouched."""
    project_data: dict[str, Any] = data.get("project", {})
    classifiers = project_data.get("classifiers", [])
    if not isinstance(classifiers, list):
        return data
    kept = [
        c
        for c in classifiers
        if not (isinstance(c, str) and c.startswith("License ::"))
    ]
    return {**data, "project": {**project_data, "classifiers": kept}}


def _parse_standard_metadata_with_retry(
    data: dict[str, Any],
    pyproject_path: Path,
    dynamic_fields: list[str],
    *,
    quiet: bool = False,
) -> tuple[StandardMetadata, dict[str, Any]]:
    """Parse *data* via ``StandardMetadata.from_pyproject()``, retrying once
    if the failure is the PEP 639 transitional classifier conflict.

    Returns ``(std, data)`` -- *data* is returned too since the retry path
    rewrites it (:func:`_drop_redundant_license_classifiers`), and
    :func:`read_pyproject` needs that rewritten mapping for its own later
    ``data.get("project", {})``/``_try_read_poetry()`` calls, not the
    original.

    *quiet* suppresses the PEP 639 transitional-state ``WARNING:`` -- for a
    caller that already emitted it once for this same file and is re-parsing
    only to apply a different, unrelated setting (e.g.
    :func:`pitloom.extract.project.resolve_project_with_lockfile`'s
    peek-then-reread), not because anything about the license/classifier
    data changed.
    """
    try:
        return (
            StandardMetadata.from_pyproject(
                data,
                project_dir=str(pyproject_path.parent),
                dynamic_metadata=dynamic_fields or None,
                allow_extra_keys=True,
            ),
            data,
        )
    except ConfigurationError as exc:
        if not _is_license_classifier_conflict(exc):
            raise ValueError(f"Failed to parse project metadata: {exc}") from exc
        # Classifiers that state no licence (a category alone) lose to
        # any `license`, a placeholder too, and are dropped silently.
        classifiers = data.get("project", {}).get("classifiers")
        states_licence = isinstance(classifiers, list) and bool(
            license_from_classifiers(c for c in classifiers if isinstance(c, str))
        )
        placeholder_dropped = (
            _drop_placeholder_license(data) if states_licence else None
        )
        # PEP 639: an SPDX `license` expression together with `License ::`
        # trove classifiers is a hard error in pyproject-metadata, yet
        # projects mid-migration declare both. Retry once without the
        # classifiers; the SPDX expression stays authoritative.
        if placeholder_dropped is not None:
            data = placeholder_dropped
        else:
            if states_licence and not quiet:
                log.warning(
                    "%s declares both an SPDX `license` expression and legacy "
                    "`License ::` classifiers -- dropping the redundant "
                    "classifiers and keeping the SPDX expression (PEP 639 "
                    "transitional state)",
                    quote_source(pyproject_path),
                )
            data = _drop_redundant_license_classifiers(data)
        try:
            return (
                StandardMetadata.from_pyproject(
                    data,
                    project_dir=str(pyproject_path.parent),
                    dynamic_metadata=dynamic_fields or None,
                    allow_extra_keys=True,
                ),
                data,
            )
        # pylint: disable-next=broad-exception-caught
        except Exception as retry_exc:
            raise ValueError(
                f"Failed to parse project metadata: {retry_exc}"
            ) from retry_exc
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        raise ValueError(f"Failed to parse project metadata: {exc}") from exc


# pylint: disable-next=too-many-locals
def read_pyproject(
    pyproject_path: Path,
    *,
    include_locked_dependencies: bool = True,
    quiet: bool = False,
    read_config: bool = True,
) -> tuple[ProjectMetadata, PitloomConfig]:
    """Read project metadata from a ``pyproject.toml`` file.

    Parses the ``[project]`` section via ``pyproject-metadata``, resolves
    dynamic versions, and reads Pitloom-specific settings from ``[tool.pitloom]``.

    ``include_locked_dependencies`` (default ``True``) is forwarded to
    :func:`_try_read_poetry`: ``poetry.lock`` is read only when it is true,
    and a build-stage caller passes ``False``.

    ``quiet`` suppresses this read's own ``WARNING:`` lines, for a second read
    of a file whose warnings the first already logged.

    Without ``read_config``, ``[tool.pitloom]`` is not parsed and the
    defaults are returned: an explicit config replaces it.

    Raises:
        FileNotFoundError: *pyproject_path* does not exist.
        ValueError: the file is not valid TOML, or its metadata or
            ``[tool.pitloom]`` settings are invalid.
    """
    if not pyproject_path.exists():
        raise FileNotFoundError(f"pyproject.toml not found at {pyproject_path}")

    data: dict[str, Any] = load_toml_file(pyproject_path)

    project_data: dict[str, Any] = data.get("project", {})
    # Without read_config an explicit config replaces [tool.pitloom], so a
    # fault in it must not fail the read.
    pitloom_config = (
        parse_pitloom_config(data, source=str(pyproject_path))
        if read_config
        else PitloomConfig()
    )

    name: str = (project_data.get("name") or "").strip()
    if not project_data or not name:
        return _read_pyproject_fallback(
            data,
            pyproject_path,
            name,
            pitloom_config,
            include_locked_dependencies=include_locked_dependencies,
            quiet=quiet,
        )

    data, dynamic_fields, version_source, description_source = prepare_dynamic_version(
        data, project_data, pyproject_path, quiet=quiet
    )
    data, readme_override = strip_missing_readme(project_data, pyproject_path, data)
    data = confine_readme_file(data, pyproject_path.parent, quiet=quiet)
    data = confine_license_file(data, pyproject_path.parent, quiet=quiet)
    data, held = hold_deep_requirements(data, quiet=quiet)

    std, data = _parse_standard_metadata_with_retry(
        data, pyproject_path, dynamic_fields, quiet=quiet
    )

    license_name, license_prov = stated_pyproject_license(
        std.license, std.classifiers, pyproject_path.parent
    )

    project_data = data.get("project", {})
    provenance = build_provenance(
        project_data, version_source, license_prov, description_source
    )
    # Presence-gated, not truthy-gated -- see AGENTS.md's "``None``/absent
    # vs ``[]``/``{}``" rule: `requires-python = ""` resolves to an empty (falsy)
    # SpecifierSet, PEP 621's equivalent of Poetry's `python = "*"`.
    if field_declared(project_data, "requires-python"):
        provenance["requires_python"] = (
            "Source: pyproject.toml | Field: project.requires-python"
        )

    metadata = ProjectMetadata(
        name=std.name,
        version=str(std.version) if std.version else None,
        description=std.description,
        readme=extract_readme(std, readme_override),
        requires_python=str(std.requires_python) if std.requires_python else None,
        license_name=license_name,
        keywords=std.keywords or [],
        authors=extract_authors(std, project_data),
        urls=std.urls or {},
        dependencies=held.restore_dependencies(
            [normalize_dependency_specifier(str(d)) for d in std.dependencies]
        ),
        provenance=provenance,
    )
    apply_in_package_license_files(
        metadata, read_license_members(pyproject_path.parent)
    )
    # Before the merge: a non-empty list wins it whole, as a static one.
    dynamic = read_setuptools_dynamic(data, pyproject_path.parent, quiet=quiet)
    dynamic.add_dependencies(metadata)
    metadata, from_poetry = fill_from_poetry(
        metadata,
        data,
        pyproject_path.parent,
        include_locked_dependencies=include_locked_dependencies,
        quiet=quiet,
    )
    dynamic.add_extras(
        metadata,
        held.restore_optional(
            {
                extra: [str(r) for r in reqs]
                for extra, reqs in std.optional_dependencies.items()
            }
        ),
        declared=field_declared(project_data, "optional-dependencies")
        and not from_poetry,
        quiet=quiet,
    )

    return metadata, pitloom_config


def fill_from_poetry(
    metadata: ProjectMetadata,
    data: dict[str, Any],
    project_dir: Path,
    *,
    include_locked_dependencies: bool,
    quiet: bool = False,
) -> tuple[ProjectMetadata, bool]:
    """*metadata*, read from ``[project]``, with its gaps filled from
    ``[tool.poetry]`` (``[project]`` fields win), and whether its
    dependency lists replace ``[project]``'s
    (:func:`~pitloom.extract.project._poetry_extras.defer_to_poetry_lists`):
    the one gap-fill of the CLI and the Hatchling hook.

    Only a Poetry build backend, or none declared, reads ``[tool.poetry]``
    (:func:`~pitloom.extract.project._poetry_extras.poetry_backend_reads`);
    for any other, a ``[tool.poetry]`` key that would fill a gap is
    reported with one ``WARNING:`` and only ``poetry.lock`` is applied.
    *include_locked_dependencies* and *quiet* are :func:`_try_read_poetry`'s.
    """
    read_fields = poetry_backend_reads(data)
    if not read_fields:
        warn_unread_poetry_fields(metadata, data, quiet=quiet)
    poetry_meta = _try_read_poetry(
        data,
        project_dir,
        include_locked_dependencies=include_locked_dependencies,
        quiet=quiet,
        read_fields=read_fields,
    )
    from_poetry = defer_to_poetry_lists(metadata, poetry_meta, data)
    if poetry_meta is not None:
        metadata = merge_project_metadata(metadata, poetry_meta)
    return metadata, from_poetry


def _try_read_poetry(
    data: dict[str, Any],
    project_dir: Path,
    *,
    include_locked_dependencies: bool = True,
    quiet: bool = False,
    read_fields: bool = True,
) -> ProjectMetadata | None:
    """Return poetry metadata when ``[tool.poetry]`` is present, else ``None``.

    Without *read_fields*, ``[tool.poetry]``'s own fields are not read:
    only ``poetry.lock`` (``None`` when it is not read either).

    When *include_locked_dependencies* is true, also reads a sibling
    ``poetry.lock`` for the resolved transitive-dependency graph
    (source-stage only; see :mod:`pitloom.extract.lock.poetry`).
    The Hatchling build hook's metadata gap-fill path
    (:func:`pitloom.extract.project.hatchling._poetry_fallback_metadata`) passes
    ``include_locked_dependencies=False``: that path runs at build/embed
    time, where a stale or unrelated ``poetry.lock`` must never influence
    the emitted SBOM.

    A malformed ``[tool.poetry]`` section (e.g. missing ``name`` -- common
    for a PEP 621 ``[project]``-primary layout that keeps ``[tool.poetry]``
    only for non-metadata settings) does not, on its own, suppress
    ``poetry.lock`` reading: the two are independent, and a project can
    have a perfectly good lock file even when its ``[tool.poetry]`` gap-fill
    metadata can't be extracted.
    """
    # Presence, not truthiness: a falsy non-table (`poetry = []`) must
    # reach extract_poetry_metadata()'s wrong-type warning.
    poetry = read_poetry_section(data, project_dir / "pyproject.toml", quiet=quiet)
    if poetry is None or poetry == {}:
        return None
    locked_dependencies = (
        extract_poetry_lock_dependencies(project_dir)
        if include_locked_dependencies
        else None
    )
    if not read_fields:
        if locked_dependencies is None:
            return None
        metadata = ProjectMetadata(name="")
    else:
        try:
            metadata = extract_poetry_metadata(data, project_dir, quiet=quiet)
        except (ValueError, KeyError) as exc:
            if locked_dependencies is None:
                return None
            # Not quiet-gated: reachable only with include_locked_dependencies,
            # which resolve_project_with_lockfile()'s peek never passes, so
            # this is the warning's one emission, never a repeat.
            log.warning(
                "%s: [tool.poetry] metadata could not be parsed (%s) -- "
                "skipping Poetry gap-fill, but still applying poetry.lock's "
                "resolved dependencies",
                quote_source(project_dir),
                exc,
            )
            metadata = ProjectMetadata(name="")
    if locked_dependencies is not None:
        metadata.locked_dependencies = locked_dependencies
        metadata.provenance["locked_dependencies"] = (
            f"Source: {POETRY_LOCK_SOURCE_NAME} | Method: resolved_lockfile"
        )
        hashes = extract_poetry_lock_hashes(project_dir, locked_dependencies)
        metadata.locked_dependency_hashes = hashes or {}
    return metadata
