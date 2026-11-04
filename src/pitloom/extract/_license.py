# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The licence facade of the project readers, using the licenseid library.

Gives a project its licence from the manifest's stated value and from its
own licence files (:func:`apply_in_package_license_files`), and the shared
``licenseid.resolve`` reading of a declared value
(:func:`resolve_declared_value`). Text detection
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
    which ``licenseid`` readings are accepted.
"""

from __future__ import annotations

import copy
import functools
import logging
from collections.abc import Mapping, Sequence
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path

from licenseid import DatabaseNotReadyError, Resolution, resolve

from pitloom.core.lfs_pointer import is_pointer_text
from pitloom.core.project import ProjectMetadata
from pitloom.core.provenance import provenance_segment
from pitloom.extract._license_classify import (
    _PY_SPDX_LICENSE_VERSION,
    ClassifiedLicense,
    classify_license,
    empty_blank_lines,
    is_listed_name,
    is_weak_licence,
    same_licence,
    tag_deprecated_license_ids,
    tag_license_normalization,
    warn_unless_expression,
)
from pitloom.extract._license_detect import (
    _LICENSE_STEMS,
    _LICENSE_SUFFIXES,
    _SPDX_LICENSE_ID_RE,
    _looks_like_spdx_license_expression,
    _looks_like_spdx_license_id,
    collect_license_candidates,
    find_license_files,
    license_candidates_from_members,
)
from pitloom.extract._license_text_match import detect_license_from_text
from pitloom.extract._licenseid_relay import relay_licenseid_warnings, say
from pitloom.extract.copyright_notices import apply_in_package_copyright

_logger = logging.getLogger(__name__)

try:
    _LICENSEID_VERSION: str | None = _pkg_version("licenseid")
except PackageNotFoundError:
    _LICENSEID_VERSION = None

__all__ = [
    "_LICENSE_STEMS",
    "_LICENSE_SUFFIXES",
    "_LICENSEID_VERSION",
    "_PY_SPDX_LICENSE_VERSION",
    "_SPDX_LICENSE_ID_RE",
    "_looks_like_spdx_license_expression",
    "_looks_like_spdx_license_id",
    "_with_tool_tag",
    "ClassifiedLicense",
    "apply_in_package_license",
    "apply_in_package_license_files",
    "classify_license",
    "clear_resolution_cache",
    "collect_license_candidates",
    "detect_independent_license",
    "detect_license_for_project",
    "detect_license_from_text",
    "empty_blank_lines",
    "find_license_files",
    "is_listed_name",
    "is_weak_licence",
    "license_from_candidates",
    "same_licence",
    "resolve_declared_value",
    "resolve_license_concluded",
    "stated_license",
    "tag_deprecated_license_ids",
    "tag_license_normalization",
    "warn_unless_expression",
]


#: How many answers of :func:`_resolved` are kept: a value asked about by
#: several callers costs one lookup.
_MAX_RESOLUTIONS = 4096


@functools.lru_cache(maxsize=_MAX_RESOLUTIONS)
def _resolved(value: str) -> Resolution:
    """``licenseid``'s reading of *value* on the SPDX License List packaged
    with it (``source="packaged"``: the same answer whatever database the
    user has, and with none). A failure raises and is not cached."""
    with relay_licenseid_warnings():
        return resolve(value, source="packaged")


def clear_resolution_cache() -> None:
    """Forget the answers of :func:`resolve_declared_value`."""
    _resolved.cache_clear()


def resolve_declared_value(value: str) -> Resolution | None:
    """``licenseid``'s reading of the declared licence *value*
    (:func:`licenseid.resolve` on its packaged SPDX License List), or
    ``None`` when there is no packaged list (a ``licenseid`` installed
    without it: its error relayed once per process, as ``licenseid``
    words it) or the resolver fails; a failure is not cached. Each caller
    gets its own copy."""
    try:
        return copy.deepcopy(_resolved(value))
    except DatabaseNotReadyError as exc:
        say(str(exc))
        return None
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        _logger.debug("Failed to resolve license value %r: %s", value, exc)
        return None


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
