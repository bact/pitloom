# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Extractor for Python project metadata from pyproject.toml.

Supports ``[project]`` (PEP 517/518/621) and ``[tool.poetry]`` sections.
When both are present, ``[project]`` values take precedence and
``[tool.poetry]`` fills any gaps.

See also: :mod:`pitloom.extract._pyproject_dynamic` for PEP 621
``dynamic`` field resolution (``prepare_dynamic_version()``, called from
:func:`read_pyproject` below).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pyproject_metadata import ConfigurationError, StandardMetadata

from pitloom.core.config import PitloomConfig, parse_pitloom_config
from pitloom.core.models import normalize_dependency_specifier
from pitloom.core.project import ProjectMetadata, merge_project_metadata
from pitloom.extract._license import (
    _looks_like_spdx_license_expression,
    _looks_like_spdx_license_id,
    detect_license_for_project,
    resolve_license_concluded,
)
from pitloom.extract._poetry import extract_poetry_metadata
from pitloom.extract._poetry_lock import extract_poetry_lock_dependencies
from pitloom.extract._pyproject_dynamic import prepare_dynamic_version
from pitloom.extract._toml_io import load_toml_file

log = logging.getLogger(__name__)


def _read_pyproject_fallback(
    data: dict[str, Any],
    pyproject_path: Path,
    name: str,
    pitloom_config: PitloomConfig,
) -> tuple[ProjectMetadata, PitloomConfig]:
    """Handle fallback when [project] section is absent or missing a name."""
    poetry_meta = _try_read_poetry(data, pyproject_path.parent)
    if poetry_meta is not None:
        return poetry_meta, pitloom_config
    license_name, license_prov = detect_license_for_project(pyproject_path.parent)
    prov: dict[str, str] = {}
    if name:
        prov["name"] = "Source: pyproject.toml | Field: project.name"
    if license_prov:
        prov["license"] = license_prov
    return (
        ProjectMetadata(name=name, license_name=license_name, provenance=prov),
        pitloom_config,
    )


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
    stable discriminator than message text for this; if a future release
    rewords the message, this check starts under-matching (silently
    stops recovering the transitional state) and needs updating."""
    return (
        exc.key == "project.license"
        and "not compatible with 'License ::' classifiers" in str(exc)
    )


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


# pylint: disable-next=too-many-locals
def read_pyproject(pyproject_path: Path) -> tuple[ProjectMetadata, PitloomConfig]:
    """Read project metadata from a ``pyproject.toml`` file.

    Parses the ``[project]`` section via ``pyproject-metadata``, resolves
    dynamic versions, and reads Pitloom-specific settings from ``[tool.pitloom]``.
    """
    if not pyproject_path.exists():
        raise FileNotFoundError(f"pyproject.toml not found at {pyproject_path}")

    data: dict[str, Any] = load_toml_file(pyproject_path)

    project_data: dict[str, Any] = data.get("project", {})
    pitloom_config = parse_pitloom_config(data)

    name: str = (project_data.get("name") or "").strip()
    if not project_data or not name:
        return _read_pyproject_fallback(data, pyproject_path, name, pitloom_config)

    data, dynamic_fields, version_source, description_source = prepare_dynamic_version(
        data, project_data, pyproject_path
    )
    data, readme_override = _strip_missing_readme(project_data, pyproject_path, data)

    try:
        std = StandardMetadata.from_pyproject(
            data,
            project_dir=str(pyproject_path.parent),
            dynamic_metadata=dynamic_fields or None,
            allow_extra_keys=True,
        )
    except ConfigurationError as exc:
        if not _is_license_classifier_conflict(exc):
            raise ValueError(f"Failed to parse project metadata: {exc}") from exc
        # PEP 639 transitional state: a project declares both a modern
        # SPDX `license` expression and legacy `License ::` trove
        # classifiers -- pyproject-metadata treats the combination as a
        # hard error. Real-world projects mid-migration commonly leave
        # the old classifiers in place rather than deleting them the
        # same release they add the SPDX field. Retry once with the
        # redundant classifiers dropped, keeping the SPDX expression --
        # the newer, more specific PEP 639 source -- as authoritative.
        log.warning(
            "%s declares both an SPDX `license` expression and legacy "
            "`License ::` classifiers -- dropping the redundant "
            "classifiers and keeping the SPDX expression (PEP 639 "
            "transitional state)",
            pyproject_path,
        )
        data = _drop_redundant_license_classifiers(data)
        try:
            std = StandardMetadata.from_pyproject(
                data,
                project_dir=str(pyproject_path.parent),
                dynamic_metadata=dynamic_fields or None,
                allow_extra_keys=True,
            )
        # pylint: disable-next=broad-exception-caught
        except Exception as retry_exc:
            raise ValueError(
                f"Failed to parse project metadata: {retry_exc}"
            ) from retry_exc
    # pylint: disable=broad-exception-caught
    except Exception as exc:
        raise ValueError(f"Failed to parse project metadata: {exc}") from exc

    license_name, license_prov = _extract_and_detect_license(std, pyproject_path.parent)

    # G2: independently scan the project directory for a second opinion to
    # compare the declared value against, via the shared resolver every
    # project-metadata extractor must call (see its docstring) -- without
    # this, a declared value that already looks like a valid SPDX id would
    # short-circuit before the LICENSE file is ever read, so there would be
    # nothing to disagree with.
    license_concluded, license_concluded_prov = resolve_license_concluded(
        bool(std.license), pyproject_path.parent
    )

    provenance = _build_provenance(
        data.get("project", {}), version_source, license_prov, description_source
    )
    if license_concluded and license_concluded_prov:
        provenance["license_concluded"] = license_concluded_prov

    metadata = ProjectMetadata(
        name=std.name,
        version=str(std.version) if std.version else None,
        description=std.description,
        readme=_extract_readme(std, readme_override),
        requires_python=str(std.requires_python) if std.requires_python else None,
        license_name=license_name,
        license_concluded=license_concluded,
        keywords=std.keywords or [],
        authors=_extract_authors(std),
        urls=std.urls or {},
        dependencies=[normalize_dependency_specifier(str(d)) for d in std.dependencies],
        provenance=provenance,
    )

    # Fill any remaining gaps from [tool.poetry] (project fields win).
    poetry_meta = _try_read_poetry(data, pyproject_path.parent)
    if poetry_meta is not None:
        metadata = merge_project_metadata(metadata, poetry_meta)

    return metadata, pitloom_config


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

_FIELD_PROVENANCE = {
    "description": "Source: pyproject.toml | Field: project.description",
    "urls": "Source: pyproject.toml | Field: project.urls",
    "dependencies": "Source: pyproject.toml | Field: project.dependencies",
    "authors": "Source: pyproject.toml | Field: project.authors",
    "license": "Source: pyproject.toml | Field: project.license",
}


def _build_provenance(
    project_data: dict[str, Any],
    version_source: str | None,
    license_prov_override: str | None = None,
    description_source: str | None = None,
) -> dict[str, str]:
    """Build the provenance dict from the raw project section data."""
    prov: dict[str, str] = {
        "name": "Source: pyproject.toml | Field: project.name",
    }
    if version_source:
        prov["version"] = version_source
    elif "version" in project_data:
        prov["version"] = "Source: pyproject.toml | Field: project.version"

    for field_key, source in _FIELD_PROVENANCE.items():
        if field_key == "description" and description_source:
            prov["description"] = description_source
        elif field_key == "license":
            # license_prov_override, when truthy, always sets prov["license"]
            # here -- nothing downstream can unset it, so no post-loop
            # fallback is needed for that case.
            if license_prov_override:
                prov["license"] = license_prov_override
            elif field_key in project_data:
                prov["license"] = source
        elif field_key in project_data:
            prov[field_key] = source

    if project_data.get("authors"):
        prov["copyright_text"] = (
            "Source: Pitloom generator | Method: inferred_from_authors"
        )

    return prov


def _strip_missing_readme(
    project_data: dict[str, Any],
    pyproject_path: Path,
    data: dict[str, Any],
) -> tuple[dict[str, Any], str | None]:
    """Remove a readme entry whose file does not exist to avoid parse errors.

    Returns the (possibly modified) data dict and an optional readme override
    value that the caller can use to preserve the declared filename.
    """
    readme_field = project_data.get("readme")
    if not (readme_field and isinstance(readme_field, str)):
        return data, None
    if (pyproject_path.parent / readme_field).exists():
        return data, None
    stripped = {
        **data,
        "project": {k: v for k, v in data["project"].items() if k != "readme"},
    }
    return stripped, readme_field


def _extract_readme(std: StandardMetadata, override: str | None) -> str | None:
    """Return the readme text or filename from StandardMetadata."""
    if override is not None:
        return override
    readme = std.readme
    if readme:
        if hasattr(readme, "file") and readme.file:
            return str(readme.file)
        if hasattr(readme, "text") and readme.text:
            return readme.text
    return None


def _resolve_license_hint(
    license_obj: Any,
    project_dir: Path,
) -> tuple[str | None, str, tuple[str | None, str | None]]:
    """Extract ``(hint, base_prov, fallback)`` from a raw license object.

    *hint* is the text or string to attempt detection on.  *fallback* is the
    ``(license_id, provenance)`` pair to return when detection finds nothing
    new.  Returns ``hint=None`` when the object format is unrecognised or the
    referenced file cannot be read.
    """
    base = "Source: pyproject.toml | Field: project.license"
    if isinstance(license_obj, str):
        # str: let detect_license_for_project provide the fallback
        return license_obj.strip(), base, (None, None)
    if hasattr(license_obj, "text") and license_obj.text:
        hint = license_obj.text
        return hint, f"{base}.text", (hint, None)
    if hasattr(license_obj, "file") and license_obj.file:
        fname = str(license_obj.file)
        try:
            text = (project_dir / fname).read_text(encoding="utf-8", errors="replace")
            return text, f"Source: {fname}", (fname, None)
        except OSError:
            return None, base, (fname, None)
    return None, base, (str(license_obj), None)


def _extract_and_detect_license(
    std: StandardMetadata,
    project_dir: Path,
) -> tuple[str | None, str | None]:
    """Return ``(license_id, provenance_override)`` from StandardMetadata.

    Handles both plain string format (PEP 639) and License object format.
    When the metadata field contains license text rather than an SPDX License ID,
    falls back to :func:`~pitloom.extract._license.detect_license_for_project`
    which searches the project directory and uses the ``licenseid`` library for
    text-based detection.

    Returns a 2-tuple:

    * ``license_id`` -- SPDX License ID, SPDX License Expression,
      or raw string fallback.
    * ``provenance_override`` -- non-``None`` when provenance differs from the
      default ``pyproject.toml`` field string (e.g. detected from a file).
    """
    license_obj = std.license
    if not license_obj:
        return detect_license_for_project(project_dir)

    hint, base_prov, fallback = _resolve_license_hint(license_obj, project_dir)
    if hint is None:
        return fallback

    if _looks_like_spdx_license_id(hint) or _looks_like_spdx_license_expression(hint):
        return hint, None

    detected, prov = detect_license_for_project(project_dir, hint)
    if detected and detected != hint:
        return detected, f"{base_prov} | Method: licenseid_detection"

    fallback_id, fallback_prov = fallback
    if fallback_id is not None:
        return fallback_id, fallback_prov
    return detected, prov


def _extract_authors(std: StandardMetadata) -> list[dict[str, str]]:
    """Return authors as a list of ``{name, email?}`` dicts."""
    result = []
    for name, email in std.authors:
        entry: dict[str, str] = {"name": name} if name else {}
        if email:
            entry["email"] = email
        if entry:
            result.append(entry)
    return result


def _try_read_poetry(
    data: dict[str, Any],
    project_dir: Path,
    *,
    include_locked_dependencies: bool = True,
) -> ProjectMetadata | None:
    """Return poetry metadata when ``[tool.poetry]`` is present, else ``None``.

    When *include_locked_dependencies* is true (the default, used by every
    ``read_pyproject()`` caller), also reads a sibling ``poetry.lock`` for
    the resolved transitive-dependency graph -- source-stage-only
    enrichment; see :mod:`pitloom.extract._poetry_lock`'s module docstring.
    The Hatchling build hook's metadata gap-fill path
    (:func:`pitloom.extract.hatchling._poetry_fallback_metadata`) passes
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
    if not data.get("tool", {}).get("poetry"):
        return None
    locked_dependencies = (
        extract_poetry_lock_dependencies(project_dir)
        if include_locked_dependencies
        else []
    )
    try:
        metadata = extract_poetry_metadata(data, project_dir)
    except (ValueError, KeyError) as exc:
        if not locked_dependencies:
            return None
        log.warning(
            "%s: [tool.poetry] metadata could not be parsed (%s) -- "
            "skipping Poetry gap-fill, but still applying poetry.lock's "
            "resolved dependencies",
            project_dir,
            exc,
        )
        metadata = ProjectMetadata(name="")
    if locked_dependencies:
        metadata.locked_dependencies = locked_dependencies
        metadata.provenance["locked_dependencies"] = (
            "Source: poetry.lock | Method: resolved_lockfile"
        )
    return metadata
