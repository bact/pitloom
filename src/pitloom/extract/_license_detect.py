# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""File and metadata scanning for project-level license files and metadata.

See also: :mod:`pitloom.extract._license` for text matching, canonicalization,
and the public facade.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable, Mapping
from pathlib import Path

from pitloom.core.lfs_pointer import log_pointer_not_read, parse_lfs_pointer
from pitloom.core.path_confine import open_inside
from pitloom.core.path_probe import UNREADABLE_FILE_WARNING, is_missing_errno
from pitloom.core.provenance import provenance_segment, provenance_source
from pitloom.logging_config import Cap, loggable, one_line, warn_once, warn_over_cap

log = logging.getLogger(__name__)

# Candidate filenames in priority order (no-extension first, then common suffixes)
_LICENSE_STEMS = ("LICENSE", "LICENCE", "COPYING", "COPYRIGHT")
_LICENSE_SUFFIXES = ("", ".txt", ".rst", ".md")

#: Root-level metadata files carrying a ``license`` field.
CITATION_CFF = "CITATION.cff"
CODEMETA_JSON = "codemeta.json"

#: Largest license file (or ``CITATION.cff``/``codemeta.json``) read for
#: detection. Real license texts are a few KiB to some tens of KiB; a
#: larger one is skipped with one ``WARNING:`` (:data:`LICENSE_FILE_CAP`).
LICENSE_FILE_MAX_BYTES = 256 * 1024
#: :data:`LICENSE_FILE_MAX_BYTES` as every reader of a licence source warns
#: of it: through :func:`~pitloom.logging_config.warn_over_cap`, with
#: ``once=True`` (one run reads a project more than once: a lock-file
#: re-read, a declared and a concluded licence, always alike).
LICENSE_FILE_CAP = Cap(LICENSE_FILE_MAX_BYTES, "byte", "license-detection")

# Heuristic: single-token SPDX License IDs and expressions like "GPL-3.0-or-later"
_SPDX_LICENSE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-+]*$")


def _looks_like_spdx_license_id(value: str) -> bool:
    """Return True when *value* looks like a bare SPDX License ID, not license text."""
    stripped = value.strip()
    return bool(
        stripped
        and "\n" not in stripped
        and len(stripped) < 100
        and _SPDX_LICENSE_ID_RE.match(stripped)
    )


def pick_license_names(names: Iterable[str]) -> list[str]:
    """The license-file names among the root-level *names*, in priority
    order, one per candidate name (``LICENSE``, ``LICENSE.txt``, ...).

    Matching ignores case. When several names differ only in case (a
    case-sensitive file system or an archive), the candidate's own
    spelling wins, else the first in plain ``str`` order -- never the
    listing order."""
    by_key: dict[str, list[str]] = {}
    for name in names:
        by_key.setdefault(name.lower(), []).append(name)
    picked: list[str] = []
    for stem in _LICENSE_STEMS:
        for suffix in _LICENSE_SUFFIXES:
            candidate = stem + suffix
            matches = by_key.get(candidate.lower())
            if matches:
                picked.append(candidate if candidate in matches else min(matches))
    return picked


def license_source_names(names: Iterable[str]) -> list[str]:
    """The root-level *names* detection reads: ``CITATION.cff`` and
    ``codemeta.json`` by exact name, then :func:`pick_license_names`."""
    names = list(names)
    exact = [name for name in (CITATION_CFF, CODEMETA_JSON) if name in names]
    return [*exact, *pick_license_names(names)]


def find_license_files(project_dir: Path) -> list[Path]:
    """Return existing license files in *project_dir* in priority order
    (see :func:`pick_license_names`)."""
    try:
        names = [p.name for p in project_dir.iterdir() if p.is_file()]
    except OSError:
        return []
    return [project_dir / name for name in pick_license_names(names)]


def decode_text(raw: bytes, errors: str = "strict") -> str:
    """*raw* as UTF-8 text with universal newlines, as
    :meth:`pathlib.Path.read_text` gives it.

    Raises:
        UnicodeDecodeError: *raw* is not UTF-8 and *errors* is ``"strict"``.
    """
    return raw.decode("utf-8", errors).replace("\r\n", "\n").replace("\r", "\n")


def _license_from_citation_cff(raw: bytes) -> str | None:
    """Extract the ``license:`` field from ``CITATION.cff`` without a YAML dep."""
    try:
        text = decode_text(raw)
    except UnicodeDecodeError:
        return None

    scalar_m = re.search(
        r'^license:\s*["\']?([A-Za-z0-9][A-Za-z0-9.\-+]*)["\']?\s*$',
        text,
        re.MULTILINE,
    )
    if scalar_m:
        return scalar_m.group(1)

    list_m = re.search(
        r'^license:\s*\n\s*-\s*["\']?([A-Za-z0-9][A-Za-z0-9.\-+]*)["\']?',
        text,
        re.MULTILINE,
    )
    if list_m:
        return list_m.group(1)

    return None


def _license_from_codemeta_json(raw: bytes) -> str | None:
    """Extract the ``license`` field from ``codemeta.json``."""
    try:
        # json.loads(bytes) strips a leading UTF-8 BOM; a decoded str would not.
        data = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None

    if not isinstance(data, dict):
        return None
    value = data.get("license", "")
    if not isinstance(value, str) or not value:
        return None

    if "/" in value:
        candidate = value.rstrip("/").rsplit("/", 1)[-1]
        candidate = re.sub(r"\.(html|txt|md)$", "", candidate, flags=re.IGNORECASE)
        return candidate if _looks_like_spdx_license_id(candidate) else None

    return value if _looks_like_spdx_license_id(value) else None


def member_source(label: str, archive: str | None, *, field: str | None = None) -> str:
    """The provenance of what *label*, a project file, held: ``Source:
    <label>``, then ``File: <archive>`` when it was read from the archive
    named *archive*, then ``Field: <field>`` when given. The names are
    untrusted and go through
    :func:`~pitloom.core.provenance.provenance_source`."""
    source = provenance_source(label, file=archive)
    return source if field is None else provenance_segment(source, "Field", field)


def license_candidates_from_members(
    members: Mapping[str, bytes], archive: str | None = None
) -> list[tuple[str, str]]:
    """Return ``[(value, source_description), ...]`` for all license
    sources among *members*: a project root's files, by exact name, to
    their bytes (``CITATION.cff``, ``codemeta.json``, the license files of
    :func:`pick_license_names`; other names are ignored). An empty or
    whitespace-only license file gives no candidate. *archive* names the
    archive the members come from (``| File: <archive>`` in each source).

    See also: :func:`collect_license_candidates`, the directory adapter.
    """
    candidates: list[tuple[str, str]] = []

    cff = members.get(CITATION_CFF)
    cff_id = _license_from_citation_cff(cff) if cff is not None else None
    if cff_id:
        candidates.append(
            (cff_id, member_source(CITATION_CFF, archive, field="license"))
        )

    codemeta = members.get(CODEMETA_JSON)
    codemeta_id = (
        _license_from_codemeta_json(codemeta) if codemeta is not None else None
    )
    if codemeta_id:
        candidates.append(
            (codemeta_id, member_source(CODEMETA_JSON, archive, field="license"))
        )

    for name in pick_license_names(members):
        text = decode_text(members[name], errors="replace")
        if text.strip():
            candidates.append((text, member_source(name, archive)))

    return candidates


def read_license_file(path: Path, root: Path | None = None) -> bytes | None:
    """*path*'s bytes, read no further than one byte past the cap; ``None``
    when it is absent, cannot be read or is over the cap. With *root*, a
    file not inside it (a symlink out) is not read
    (:func:`~pitloom.core.path_confine.open_inside`): its content is no
    part of the project. A file present but not read is warned about, once
    per file and process. A Git LFS pointer is no licence text: ``None``, with
    a ``DEBUG`` line only (one among the project's files is also in the
    run's one pointer warning)."""
    try:
        with path.open("rb") if root is None else open_inside(path, root) as fh:
            raw = fh.read(LICENSE_FILE_MAX_BYTES + 1)
    except OSError as exc:
        if not is_missing_errno(exc):
            warn_once(
                log,
                f"license-unreadable:{path}",
                UNREADABLE_FILE_WARNING,
                loggable(str(path)),
                "for license files",
                one_line(exc),
            )
        return None
    if len(raw) > LICENSE_FILE_MAX_BYTES:
        warn_over_cap(log, LICENSE_FILE_CAP, str(path), once=True)
        return None
    pointer = parse_lfs_pointer(raw)
    if pointer is not None:
        # Text standing in for a file not pulled: no licence text.
        log_pointer_not_read(str(path), pointer)
        return None
    return raw


def read_license_members(project_dir: Path) -> dict[str, bytes]:
    """The licence sources in *project_dir* (``CITATION.cff``,
    ``codemeta.json`` and :func:`find_license_files`), name to bytes, as
    :func:`license_candidates_from_members` takes them. A source resolving
    outside *project_dir* (a symlink out) is not read
    (:func:`read_license_file`)."""
    members: dict[str, bytes] = {}
    paths = [project_dir / CITATION_CFF, project_dir / CODEMETA_JSON]
    for path in [*paths, *find_license_files(project_dir)]:
        raw = read_license_file(path, project_dir)
        if raw is not None:
            members[path.name] = raw
    return members


def collect_license_candidates(project_dir: Path) -> list[tuple[str, str]]:
    """Return ``[(value, source_description), ...]`` for all license
    sources in *project_dir* (see :func:`license_candidates_from_members`)."""
    return license_candidates_from_members(read_license_members(project_dir))
