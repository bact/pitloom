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

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from pyproject_metadata import License

from pitloom.extract._core_metadata import license_or_classifier
from pitloom.extract._license import stated_license
from pitloom.extract._license_detect import decode_text

_CLASSIFIER_PROVENANCE = "Source: pyproject.toml | Field: project.classifiers"


def _resolve_license_hint(
    license_obj: Any,
    project_dir: Path | None,
) -> tuple[str | None, str, tuple[str | None, str | None]]:
    """Extract ``(hint, base_prov, fallback)`` from a raw license object.

    *hint* is the text or string to attempt detection on.  *fallback* is the
    ``(license_id, provenance)`` pair to return when detection finds nothing
    new.  Returns ``hint=None`` when the object format is unrecognised or the
    referenced file cannot be read (or there is no *project_dir*).
    """
    base = "Source: pyproject.toml | Field: project.license"
    if isinstance(license_obj, str):
        return license_obj, base, (None, None)
    if hasattr(license_obj, "text") and license_obj.text:
        hint = license_obj.text
        return hint, f"{base}.text", (hint, None)
    if project_dir is not None and getattr(license_obj, "file", None):
        fname = str(license_obj.file)
        try:
            text = (project_dir / fname).read_text(encoding="utf-8", errors="replace")
            return text, f"Source: {fname}", (fname, None)
        except OSError:
            return None, base, (fname, None)
    return None, base, (str(license_obj), None)


def stated_pyproject_license(
    license_obj: Any,
    classifiers: Iterable[str],
    project_dir: Path | None,
) -> tuple[str | None, str | None]:
    """Return ``(license_id, provenance_override)`` for the licence a
    ``[project]`` table states.

    ``project.license`` first (*license_obj*: a PEP 639 string, or a
    ``text``/``file`` table whose text ``licenseid`` may identify), then,
    when that states no licence or only ``UNKNOWN``/``NOASSERTION``, a
    ``License ::`` classifier
    (:func:`~pitloom.extract._core_metadata.license_or_classifier`, the rule
    a wheel and an sdist use). The project's own licence files are not read
    here: :func:`~pitloom.extract._license.apply_in_package_license` adds
    them, on every reader alike.

    Returns a 2-tuple:

    * ``license_id`` -- SPDX License ID, SPDX License Expression,
      the licence as written, or ``None``.
    * ``provenance_override`` -- non-``None`` when provenance differs from the
      default ``pyproject.toml`` field string (e.g. detected from a file).
    """
    license_id, provenance = (
        _license_from_field(license_obj, project_dir) if license_obj else (None, None)
    )
    license_id, from_classifier = license_or_classifier(license_id, classifiers)
    if from_classifier:
        return license_id, _CLASSIFIER_PROVENANCE
    return license_id, provenance


def _license_from_field(
    license_obj: Any, project_dir: Path | None
) -> tuple[str | None, str | None]:
    """``(license_id, provenance_override)`` from a stated ``project.license``;
    a method is recorded only when ``licenseid`` identified its text."""
    hint, base_prov, fallback = _resolve_license_hint(license_obj, project_dir)
    if hint is None:
        return fallback
    detected, prov = stated_license(hint, base_prov)
    if prov or detected != hint:
        # Identified text, or an id once stripped: the value read.
        return detected, prov or base_prov
    fallback_id, fallback_prov = fallback
    if fallback_id is not None:
        return fallback_id, fallback_prov
    return detected, None


def license_from_project_table(
    project: dict[str, Any], read_file: Callable[[str], bytes | None]
) -> tuple[str | None, str | None]:
    """:func:`stated_pyproject_license` for a raw ``[project]`` table, read
    without ``pyproject-metadata`` (an sdist with no ``PKG-INFO``): a
    ``project.license`` string, or a table with exactly one of ``text`` or
    ``file`` (*read_file* gives that file's bytes, ``None`` when it has
    none), as ``pyproject-metadata`` reads it; any other shape states
    nothing. ``project.classifiers`` follow as for a directory."""
    raw = project.get("license")
    license_obj: Any = raw if isinstance(raw, str) else None
    if isinstance(raw, dict) and bool(raw.get("text")) != bool(raw.get("file")):
        text, file = raw.get("text"), raw.get("file")
        if isinstance(file, str):
            content = read_file(file)
            text = None if content is None else decode_text(content, "replace")
        if isinstance(text, str):
            license_obj = License(text, None)
    classifiers = project.get("classifiers")
    names = (
        [c for c in classifiers if isinstance(c, str)]
        if isinstance(classifiers, list)
        else []
    )
    return stated_pyproject_license(license_obj, names, None)
