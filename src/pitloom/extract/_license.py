# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The licence facade of the project readers, using the licenseid library.

Gives a project its licence from the manifest's stated value and from its
own licence files (:func:`apply_in_package_license_files`), and re-exports
the shared ``licenseid.resolve`` reading of a declared value
(:func:`~pitloom.extract._license_resolve.resolve_declared_value`). Text
detection
(:func:`~pitloom.extract._license_text_match.detect_license_from_text`)
requires a populated database; the reading of a declared value (``Apache2``
-> ``Apache-2.0``) uses the SPDX License List packaged with ``licenseid``
and needs none, as other sources (``CITATION.cff``, ``codemeta.json``) do
not.

Every ``licenseid`` call runs inside
:func:`pitloom.extract._licenseid_relay.relay_licenseid_warnings`.

See Also:
    :mod:`pitloom.extract._license_text_match` for licence text detection,
    :mod:`pitloom.extract._license_detect` for file candidate scanning,
    :mod:`pitloom.extract._license_classify` for classifying a value
    (re-exported here), and :mod:`pitloom.extract._license_resolve` for
    the reading of a declared value.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path

from pitloom.core.lfs_pointer import is_pointer_text
from pitloom.core.project import ProjectMetadata
from pitloom.core.provenance import provenance_segment
from pitloom.extract._license_classify import (
    classify_license,
    empty_blank_lines,
    is_weak_licence,
    tag_deprecated_license_ids,
    tag_license_normalization,
    warn_unless_expression,
)
from pitloom.extract._license_detect import (
    _looks_like_spdx_license_expression,
    _looks_like_spdx_license_id,
    collect_license_candidates,
    license_candidates_from_members,
)
from pitloom.extract._license_resolve import (
    clear_resolution_cache,
    resolve_declared_value,
)
from pitloom.extract._license_text_match import detect_license_from_text
from pitloom.extract.copyright_notices import apply_in_package_copyright

_logger = logging.getLogger(__name__)

try:
    _LICENSEID_VERSION: str | None = _pkg_version("licenseid")
except PackageNotFoundError:
    _LICENSEID_VERSION = None

__all__ = [
    "_LICENSEID_VERSION",
    "_with_tool_tag",
    "apply_in_package_license",
    "apply_in_package_license_files",
    "classify_license",
    "clear_resolution_cache",
    "detect_independent_license",
    "detect_license_for_project",
    "empty_blank_lines",
    "is_weak_licence",
    "resolve_declared_value",
    "resolve_license_concluded",
    "stated_license",
    "tag_deprecated_license_ids",
    "tag_license_normalization",
    "warn_unless_expression",
]


def _with_tool_tag(provenance: str) -> str:
    """Append the ``licenseid`` library version to a detection provenance string."""
    if _LICENSEID_VERSION is None:
        return provenance
    return provenance_segment(provenance, "Tool", f"licenseid=={_LICENSEID_VERSION}")


def license_from_candidates(
    candidates: Sequence[tuple[str, str]], *, stated: str | None = None
) -> tuple[str, str] | None:
    """``(id, provenance)`` from the first of *candidates* (see
    :func:`~pitloom.extract._license_detect.license_candidates_from_members`)
    that states an id or expression, or whose text ``licenseid`` identifies
    (the manifest's *stated* licence winning a near-tie, see
    :func:`detect_license_from_text`); ``None`` when none does."""
    for value, source in candidates:
        if _looks_like_spdx_license_id(value) or _looks_like_spdx_license_expression(
            value
        ):
            return value, source
        detected = detect_license_from_text(value, stated=stated)
        if detected:
            return detected, _with_tool_tag(
                provenance_segment(source, "Method", "licenseid_detection")
            )
    return None


def detect_independent_license(
    project_dir: Path, *, stated: str | None = None
) -> tuple[str | None, str | None]:
    """Detect a license purely from project-directory files (*stated*: see
    :func:`license_from_candidates`)."""
    found = license_from_candidates(
        collect_license_candidates(project_dir), stated=stated
    )
    return found if found is not None else (None, None)


def resolve_license_concluded(
    has_declared_license: bool, project_dir: Path, *, stated: str | None = None
) -> tuple[str | None, str | None]:
    """Return ``(concluded_id, concluded_provenance)`` (G2 second opinion;
    *stated*, the declared licence: see :func:`license_from_candidates`)."""
    if not has_declared_license:
        return None, None
    return detect_independent_license(project_dir, stated=stated)


def apply_in_package_license(
    metadata: ProjectMetadata, candidates: Sequence[tuple[str, str]]
) -> None:
    """Record what the project's own licence files say (*candidates*, see
    :func:`license_from_candidates`) on *metadata*, the one rule for every
    project reader (:func:`apply_in_package_license_files`): when the manifest
    states a licence (``license_name`` not blank), the detection is the
    concluded second opinion (G2); when it is silent, the declared licence.
    Nothing changes when no candidate gives a licence."""
    stated = (metadata.license_name or "").strip()
    found = license_from_candidates(candidates, stated=stated)
    if found is None:
        return
    detected, provenance = found
    if stated:
        metadata.license_concluded = detected
        metadata.provenance["license_concluded"] = provenance
    else:
        metadata.license_name = detected
        metadata.provenance["license"] = provenance


def apply_in_package_license_files(
    metadata: ProjectMetadata,
    members: Mapping[str, bytes],
    archive: str | None = None,
) -> None:
    """Record what the project's own licence sources say on *metadata*,
    the one call every project reader (directory, Hatchling hook, sdist)
    makes: its licence (:func:`apply_in_package_license`) and the copyright
    notices found (:func:`~pitloom.extract.copyright_notices.\
apply_in_package_copyright`). *members* maps a root-level name to its bytes
    (:func:`~pitloom.extract._license_detect.read_license_members` for a
    directory); *archive* names the archive they come from."""
    apply_in_package_license(
        metadata, license_candidates_from_members(members, archive)
    )
    apply_in_package_copyright(metadata, members, archive)


def detect_license_for_project(
    project_dir: Path,
    license_hint: str | None = None,
    hint_source: str = "",
) -> tuple[str | None, str | None]:
    """Detect an SPDX license ID for a project, returning ``(id, provenance)``.

    A stated *license_hint* is the manifest's own licence: an id or an
    expression is returned stripped; text that ``licenseid`` identifies gives
    the id, with *hint_source* and the method in the provenance; other text
    is returned as written, with no provenance (no detection happened). The
    project directory is read only when no hint is stated: against a stated
    licence it is the G2 second opinion (:func:`resolve_license_concluded`),
    not a replacement.
    """
    if not (license_hint or "").strip():
        return detect_independent_license(project_dir)
    return stated_license(license_hint, hint_source)


def stated_license(
    license_hint: str | None, hint_source: str = ""
) -> tuple[str | None, str | None]:
    """``(id, provenance)`` for the licence a manifest states, *license_hint*:
    an id or an expression stripped; text that ``licenseid`` identifies, the
    id, with *hint_source* and the method in the provenance; other text as
    written, with no provenance. ``(None, None)`` when blank, or when the
    whole hint is a Git LFS pointer (a licence file not pulled, read by a
    build backend as its text: no licence text); the project's own files
    are not read here (:func:`apply_in_package_license`)."""
    hint = (license_hint or "").strip()
    if not hint or is_pointer_text(license_hint or ""):
        return None, None
    if _looks_like_spdx_license_id(hint) or _looks_like_spdx_license_expression(hint):
        return hint, None
    detected = detect_license_from_text(hint)
    if detected:
        method = "Method: licenseid_detection"
        return detected, _with_tool_tag(
            f"{hint_source} | {method}" if hint_source else method
        )
    return license_hint, None
