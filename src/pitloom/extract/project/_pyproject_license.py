# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The licence a ``pyproject.toml`` ``[project]`` table states.

See also: :mod:`pitloom.extract.project.pyproject` (the reader that calls
this) and :mod:`pitloom.extract._core_metadata` (the classifier rule a
wheel and an sdist share).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pyproject_metadata import StandardMetadata

from pitloom.extract._core_metadata import license_or_classifier
from pitloom.extract._license import detect_license_for_project

_CLASSIFIER_PROVENANCE = "Source: pyproject.toml | Field: project.classifiers"


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
        return license_obj, base, (None, None)
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

    ``project.license`` first (PEP 639 string, or a ``text``/``file`` table
    whose text :func:`~pitloom.extract._license.detect_license_for_project`
    may identify), then, when that states no licence or only
    ``UNKNOWN``/``NOASSERTION``, a ``License ::`` classifier
    (:func:`~pitloom.extract._core_metadata.license_or_classifier`, the rule
    a wheel and an sdist use), then the project directory.

    Returns a 2-tuple:

    * ``license_id`` -- SPDX License ID, SPDX License Expression,
      or the licence as written.
    * ``provenance_override`` -- non-``None`` when provenance differs from the
      default ``pyproject.toml`` field string (e.g. detected from a file).
    """
    license_id, provenance = (
        _license_from_field(std.license, project_dir) if std.license else (None, None)
    )
    license_id, from_classifier = license_or_classifier(license_id, std.classifiers)
    if from_classifier:
        return license_id, _CLASSIFIER_PROVENANCE
    if license_id is None:
        return detect_license_for_project(project_dir)
    return license_id, provenance


def _license_from_field(
    license_obj: Any, project_dir: Path
) -> tuple[str | None, str | None]:
    """``(license_id, provenance_override)`` from a stated ``project.license``;
    a method is recorded only when ``licenseid`` identified its text."""
    hint, base_prov, fallback = _resolve_license_hint(license_obj, project_dir)
    if hint is None:
        return fallback
    detected, prov = detect_license_for_project(project_dir, hint, base_prov)
    if prov or detected != hint:
        # Identified text, or an id once stripped: the value read.
        return detected, prov or base_prov
    fallback_id, fallback_prov = fallback
    if fallback_id is not None:
        return fallback_id, fallback_prov
    return detected, None
