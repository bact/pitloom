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
import re
from pathlib import Path

# Candidate filenames in priority order (no-extension first, then common suffixes)
_LICENSE_STEMS = ("LICENSE", "LICENCE", "COPYING", "COPYRIGHT")
_LICENSE_SUFFIXES = ("", ".txt", ".rst", ".md")

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


def find_license_files(project_dir: Path) -> list[Path]:
    """Return existing license files in *project_dir* in priority order."""
    try:
        actual: dict[str, Path] = {
            p.name.lower(): p for p in project_dir.iterdir() if p.is_file()
        }
    except OSError:
        return []

    seen: set[str] = set()
    found: list[Path] = []
    for stem in _LICENSE_STEMS:
        for suffix in _LICENSE_SUFFIXES:
            name_key = (stem + suffix).lower()
            if name_key not in seen and name_key in actual:
                seen.add(name_key)
                found.append(actual[name_key])
    return found


def _read_license_from_citation_cff(project_dir: Path) -> str | None:
    """Extract the ``license:`` field from ``CITATION.cff`` without a YAML dep."""
    cff_path = project_dir / "CITATION.cff"
    if not cff_path.exists():
        return None
    try:
        text = cff_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
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


def _read_license_from_codemeta_json(project_dir: Path) -> str | None:
    """Extract the ``license`` field from ``codemeta.json``."""
    codemeta_path = project_dir / "codemeta.json"
    if not codemeta_path.exists():
        return None
    try:
        data = json.loads(codemeta_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None

    value = data.get("license", "")
    if not isinstance(value, str) or not value:
        return None

    if "/" in value:
        candidate = value.rstrip("/").rsplit("/", 1)[-1]
        candidate = re.sub(r"\.(html|txt|md)$", "", candidate, flags=re.IGNORECASE)
        return candidate if _looks_like_spdx_license_id(candidate) else None

    return value if _looks_like_spdx_license_id(value) else None


def collect_license_candidates(project_dir: Path) -> list[tuple[str, str]]:
    """Return ``[(value, source_description), ...]`` for all license sources."""
    candidates: list[tuple[str, str]] = []

    cff_id = _read_license_from_citation_cff(project_dir)
    if cff_id:
        candidates.append((cff_id, "Source: CITATION.cff | Field: license"))

    codemeta_id = _read_license_from_codemeta_json(project_dir)
    if codemeta_id:
        candidates.append((codemeta_id, "Source: codemeta.json | Field: license"))

    for lf in find_license_files(project_dir):
        try:
            text = lf.read_text(encoding="utf-8", errors="replace")
            if text.strip():
                rel = lf.relative_to(project_dir).as_posix()
                candidates.append((text, f"Source: {rel}"))
        except OSError:
            pass

    return candidates
