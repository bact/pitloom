# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Path-key rules of the order matrix (``M/*``, ``N/*``, ``S/*``), read
from the registry file and the SBOMs, never from registry code:

- ``M/stem-key``: a model's registry key is its file's own key (a path
  below the registry root, or that key's layout alias), never its stem.
- ``M/distinct-ids``: two model files, even with one stem, hold two ids.
- ``N/nfc``, ``N/case``: a path key is NFC and spelt as on disk.
- ``S/dotdot``: no key holds a ``..`` or an absolute path (a script run
  from a subdirectory names ``../data/t.txt``).
- ``S/dataset-pin``: a loom run's dataset carries the id `id generate`
  pinned for the same file (a path from the script's own directory).

The shared mapping from an SBOM element to its registry key
(:func:`registry_key`) and the alias-aware lookup (:func:`held`) are used
by ``_order_invariants.py`` for every type.

See also: ``_order_invariants.py``, ``_order_capture.py``.
"""

from __future__ import annotations

import posixpath
import unicodedata
from collections.abc import Mapping
from pathlib import PurePosixPath

from _order_capture import (
    AI,
    DATASET,
    FILE,
    GATED,
    LOOM_SURFACES,
    PACKAGE,
    Element,
    Entry,
    Key,
)
from _order_fixtures import DATASET_DIR, DATASET_FILE, Profile

from pitloom.id_registry.keys import alias_tail, is_layout_alias

Registry = Mapping[Key, Entry]
#: (code, key, message) of one broken rule.
Finding = tuple[str, Key | None, str]


def registry_key(profile: Profile, surface: str, elem: Element) -> Key | None:
    """The registry key *elem* is looked up under. A model is named by its
    stem in every SBOM but keyed by its file: the one project model with
    that stem (case-folded: a path typed in upper case names the same file),
    for a loom run the profile's own when several share the stem, and
    ``None`` when the file cannot be told (a wheel or project SBOM with two
    models of one stem)."""
    if elem.key[0] != AI:
        return elem.key
    stem = elem.name.casefold()
    files = [p for p in profile.model_paths if PurePosixPath(p).stem.casefold() == stem]
    if len(files) == 1:
        return AI, files[0]
    if len(files) > 1 and surface in LOOM_SURFACES and profile.model:
        return AI, profile.model
    return None


def held(reg: Registry, key: Key, sha: str | None) -> tuple[Key, Entry] | None:
    """The entry *key* resolves to in *reg*: its own (a gated type's with
    the same sha256, or none), else a held layout alias of it with the same
    sha256 (a lookup never crosses a hash)."""
    entry = reg.get(key)
    if entry is not None and (
        key[0] not in GATED or sha is None or entry.sha in (None, sha)
    ):
        return key, entry
    for other in sorted(reg):
        if (
            other[0] == key[0]
            and is_layout_alias(key[1], other[1])
            and sha is not None
            and reg[other].sha == sha
        ):
            return other, reg[other]
    return None


#: The surfaces whose file names are distribution paths (an sdist's, a
#: wheel's), not the project path a registry keys a file by; "" is an
#: imported SBOM, whose surface is unknown.
_NAMED_BY_DISTRIBUTION = ("project", "sdist", "")


def candidates(
    profile: Profile, surface: str, elem: Element, disk: Mapping[str, str]
) -> list[Key]:
    """The registry keys *elem* may be held under, best first: a model's
    file key; a project file's physical path (one that ends in its
    distribution path: ``src/`` or a monorepo's subdirectory), then its
    own name (an sdist's also without its ``<name>-<version>/`` prefix); an
    embed's member below the profile's project directory.
    Empty when the model file cannot be told (:func:`registry_key`)."""
    type_name, name = elem.key
    if type_name == AI:
        key = registry_key(profile, surface, elem)
        if key is None:
            return []
        tail = alias_tail(key[1])  # a wheel's lookup is by its dist path
        return [key] + (
            [] if tail is None or surface in LOOM_SURFACES else [(AI, tail)]
        )
    if type_name == DATASET and profile.loom_dir:
        # Named as the script wrote it, keyed from the registry root.
        here = posixpath.join(profile.loom_dir, name)
        return [(DATASET, posixpath.normpath(here)), elem.key]
    if type_name == FILE and surface in _NAMED_BY_DISTRIBUTION:
        names = [name]
        if surface == "sdist" and "/" in name:
            names.append(name.partition("/")[2])  # the <name>-<version>/ prefix
        physical = [p for n in names for p in sorted(disk) if p.endswith("/" + n)]
        return [(FILE, p) for p in physical] + [(FILE, n) for n in names]
    if type_name == FILE and surface == "embed" and profile.subdir:
        # `embed-wheel --project-dir`: a member is keyed below the prefix.
        return [(FILE, posixpath.join(profile.subdir, name)), elem.key]
    return [elem.key]


def find(reg: Registry, cands: list[Key], sha: str | None) -> tuple[Key, Entry] | None:
    """The first of *cands* that :func:`held` resolves in *reg*."""
    for key in cands:
        found = held(reg, key, sha)
        if found is not None:
            return found
    return None


def expected_hit(
    elem: Element, cands: list[Key], before: Registry
) -> tuple[Key, Entry] | None:
    """The registry entry *elem*'s lookup must hit (section 7), or ``None``
    when the lookup is gated and the content differs. A package or a
    directory is ungated; a file, a model and a dataset hit the entry under
    their key, or its layout alias, when the sha256 is the same (a dataset
    entry with none, an explicit pin, is a hit for any content)."""
    type_name = elem.key[0]
    if type_name == PACKAGE or (type_name == FILE and not elem.sha):
        entry = before.get(elem.key)  # ungated (a File: a directory)
        return (elem.key, entry) if entry else None
    found = find(before, cands, elem.sha)
    if found is None:
        return None
    if type_name == DATASET and found[1].sha is None:
        return found
    return found if found[1].sha and found[1].sha == elem.sha else None


def model_rules(profile: Profile, reg: Registry) -> list[Finding]:
    """``M/*`` over one registry."""
    files = profile.model_paths
    found: list[Finding] = []
    for key in sorted(reg):
        owned = any(key[1] == p or is_layout_alias(key[1], p) for p in files)
        if key[0] == AI and not owned:
            found.append(
                ("M/stem-key", key, f"{reg[key].spdx_id} is no model file's key")
            )
    ids: dict[str, str] = {}
    for path in files:
        entry = reg.get((AI, path))
        if entry is None:
            continue
        other = ids.setdefault(entry.spdx_id, path)
        if other != path:
            found.append(
                ("M/distinct-ids", (AI, path), f"{entry.spdx_id} also {other}")
            )
    return found


def spelling_rules(reg: Registry, disk: Mapping[str, str]) -> list[Finding]:
    """``N/*`` and ``S/dotdot`` over one registry; *disk*: project path ->
    sha256 (NFC)."""
    spelt = {path.casefold(): path for path in disk}
    found: list[Finding] = []
    for key in sorted(reg):
        name = key[1]
        if key[0] not in (FILE, AI, DATASET):
            continue
        if unicodedata.normalize("NFC", name) != name:
            found.append(("N/nfc", key, "key is not NFC"))
        real = spelt.get(name.casefold())
        if real is not None and real != name and key[0] != DATASET:
            found.append(("N/case", key, f"on disk as {real}"))
        if ".." in name.split("/") or name.startswith("/"):
            found.append(("S/dotdot", key, "key is not below the registry root"))
    return found


def dataset_pins(
    op: str,
    surface: str,
    graph: list[dict[str, object]],
    before: Registry,
    disk: Mapping[str, str],
) -> list[Finding]:
    """``S/dataset-pin``: each dataset file or directory `id generate`
    pinned (a file not changed since) is carried by the loom run's SBOM
    under the pinned id: the training file and directory, the evaluation
    file."""
    if surface not in LOOM_SURFACES:
        return []
    ids = {e.get("spdxId") for e in graph if e.get("type") == DATASET}
    found: list[Finding] = []
    names = (DATASET_FILE, DATASET_DIR) if op.startswith("train") else (DATASET_FILE,)
    for name in names:
        entry = before.get((DATASET, name))
        if entry is None or (entry.sha and name in disk and entry.sha != disk[name]):
            continue
        if entry.spdx_id not in ids:
            found.append(("S/dataset-pin", (DATASET, name), f"{entry.spdx_id} absent"))
    return found
