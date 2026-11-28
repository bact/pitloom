# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""An installed dependency's licence files, and the licence they name when
its Core Metadata names none.

The files are those its ``License-File`` headers list, by exact path (PEP
639: under ``.dist-info/licenses/``, else at the ``.dist-info`` root, where
older back-ends put them); with no header, the licence files at the
``.dist-info`` root by name (``LICENSE``, ``COPYING``, ...). Each is read
capped and confined to its ``.dist-info``.

See also: :mod:`pitloom.assemble.spdx3.deps_installed` (the caller) and
:func:`pitloom.extract._license.license_from_candidates` (the reading rule
shared with a project's own licence files).
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import distribution as get_pkg_distribution
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pitloom.core._models_wheel_types import is_dist_info_path
from pitloom.core.provenance import provenance_segment
from pitloom.extract._core_metadata import (
    licence_classifier_names,
    license_from_classifiers,
)
from pitloom.extract._license import (
    classify_license,
    license_from_candidates,
    stated_text_agrees,
)
from pitloom.extract._license_classify import tag_license_normalization
from pitloom.extract._license_detect import pick_license_names
from pitloom.extract.copyright_notices import read_license_text

if TYPE_CHECKING:
    from pitloom.extract._extract_utils import CoreMetadata

#: Kinds of a Core Metadata licence that name no SPDX licence: the licence
#: files may.
_UNNAMED_KINDS = frozenset({"text", "noassertion"})


def read_dist_info_text(candidate: Any, dist: Any) -> str | None:
    """The text of the installed file *candidate* (an
    :class:`importlib.metadata.PackagePath` of the distribution *dist*)
    when it is under a ``.dist-info`` and resolves inside it, whatever its
    ``RECORD`` entry spells (``..``, a symlink out)
    (:func:`~pitloom.extract.copyright_notices.read_license_text`: capped, a
    present file that is not read warned about, by its ``RECORD`` entry);
    else ``None``."""
    entry = str(candidate)
    if not is_dist_info_path(entry):
        return None
    dist_info = Path(dist.locate_file(entry.split("/", 1)[0]))
    return read_license_text(Path(candidate.locate()), dist_info, shown=entry)


def _listed_path(dist_info: str, value: str, entries: dict[str, Any]) -> str | None:
    """The ``RECORD`` entry the ``License-File`` *value* names: under
    ``<dist_info>/licenses/`` (PEP 639), else at the ``<dist_info>`` root;
    ``None`` when neither is in *entries*, or when *value* holds a NUL
    (it names no file)."""
    if "\x00" in value:
        return None
    for path in (f"{dist_info}/licenses/{value}", f"{dist_info}/{value}"):
        if path in entries:
            return path
    return None


def dist_license_files(dist: Any, license_files: list[str]) -> list[Any]:
    """The licence files of the installed distribution *dist*, in order and
    once each: for each of *license_files* (its ``License-File`` values),
    ``<dist-info>/licenses/<value>``, else ``<dist-info>/<value>``; with
    none, the licence files at the ``<dist-info>`` root by name
    (:func:`~pitloom.extract._license_detect.pick_license_names`). Only
    entries of its ``RECORD`` count; ``[]`` without a ``.dist-info``."""
    by_entry = {str(f): f for f in dist.files or () if is_dist_info_path(str(f))}
    tops = sorted({entry.split("/", 1)[0] for entry in by_entry})
    if not tops:
        return []
    dist_info = tops[0]
    if license_files:
        found = [
            path
            for value in license_files
            if (path := _listed_path(dist_info, value, by_entry)) is not None
        ]
    else:
        root = {
            entry.split("/", 1)[1]: entry
            for entry in by_entry
            if entry.startswith(f"{dist_info}/") and entry.count("/") == 1
        }
        found = [root[name] for name in pick_license_names(root)]
    return [by_entry[entry] for entry in dict.fromkeys(found)]


def license_from_dist_files(
    dist_name: str,
    pkg_meta: CoreMetadata,
    stated: str | None,
    source: str,
) -> tuple[str, str] | None:
    """``(licence, provenance)`` from the installed licence files of
    *dist_name* when its Core Metadata licence *stated* names no SPDX
    licence (absent, ``UNKNOWN``/``NOASSERTION``, or text such as a
    classifier's own name ``Apache Software License``); else ``None``. The
    files are read by :func:`dist_license_files`, the rule by
    :func:`~pitloom.extract._license.license_from_candidates`: the first
    file LicenseID identifies, none after a file holding the texts of
    several licences; the licence its ``License ::`` classifiers name wins a
    near-tie (a verbatim LGPL-3.0 text scores ``-only`` and ``-or-later``
    alike; ``LGPLv3+`` says which). Each provenance is *source* with the
    file's ``RECORD`` entry as ``File``.

    ``None`` too when the ``License ::`` classifiers name several licences
    (python-dateutil's ``BSD License`` and ``Apache Software License``): a
    dual licence whose files LicenseID reads as one would narrow it."""
    classified = classify_license(stated, warn=False)
    if classified is not None and classified.kind not in _UNNAMED_KINDS:
        return None
    if len(licence_classifier_names(pkg_meta.get_all("Classifier") or [])) > 1:
        return None
    try:
        dist = get_pkg_distribution(dist_name)
    except PackageNotFoundError:
        return None
    files = dist_license_files(dist, pkg_meta.get_all("License-File") or [])
    candidates = [
        (text, provenance_segment(source, "File", str(path)))
        for path in files
        if (text := read_dist_info_text(path, dist)) is not None
    ]
    if not candidates:
        return None
    return license_from_candidates(candidates, stated=_classifier_expression(pkg_meta))


def with_dist_license_files(
    dist_name: str,
    pkg_meta: CoreMetadata,
    stated: tuple[str | None, str],
    source: str,
) -> tuple[str | None, str, tuple[str, str] | tuple[None, None]]:
    """``(licence, provenance, (other, provenance))`` for *dist_name* from
    its Core Metadata licence *stated* ``(licence, provenance)`` and its
    licence files (:func:`license_from_dist_files`), each the originator's
    declaration: an absent or blank licence, or ``UNKNOWN``/``NOASSERTION``
    (a placeholder, no claim), gives way to the files' licence; stated text
    LicenseID reads as the files' licence (a ``License`` header holding the
    licence body, the classifiers' licence winning a near-tie:
    :func:`~pitloom.extract._license.stated_text_agrees`) is that licence,
    its provenance keeping the text as ``Normalized-From``; other stated
    text (``Apache Software License``) stays, the files' licence a second
    declared licence (``other``). ``(None, None)`` when there is none."""
    license_id, provenance = stated
    found = license_from_dist_files(dist_name, pkg_meta, license_id, source)
    if found is None:
        return license_id, provenance, (None, None)
    classified = classify_license(license_id, warn=False)
    if classified is None or classified.kind != "text":
        return found[0], found[1], (None, None)
    text = str(license_id)
    if stated_text_agrees(text, found[0], hint=_classifier_expression(pkg_meta)):
        noted = tag_license_normalization(found[1], text, found[0], resolver=False)
        return found[0], noted, (None, None)
    return license_id, provenance, found


def _classifier_expression(pkg_meta: CoreMetadata) -> str | None:
    """The SPDX expression the ``License ::`` classifiers of *pkg_meta*
    name, or ``None`` when they name none (``Apache Software License`` has
    no version)."""
    named = classify_license(
        license_from_classifiers(pkg_meta.get_all("Classifier") or []), warn=False
    )
    return named.value if named is not None and named.kind == "expression" else None


__all__ = [
    "dist_license_files",
    "license_from_dist_files",
    "read_dist_info_text",
    "with_dist_license_files",
]
