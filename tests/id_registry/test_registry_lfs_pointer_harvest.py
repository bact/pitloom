# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Harvest records a Git LFS pointer's ``oid``, the hash its lookup gated
on, not the pointer text's digest an archive's SBOM states; every reader of
an element's hash (``_own_sha256``, ``_stale``, ``unique_file_keys``) takes
it from one helper, ``harvest_sha256``, so they agree. A project with no
pointer harvests and states exactly what it did before. A merged
fragment's element stating the ``oid`` at the pointer's path is the same
content (its twin): the run's element is written.

See also: test_registry_lfs_pointer_order.py (the route-and-order matrix),
tests/core/test_file_hash_stated.py (``ProjectFile.registry_sha256``).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.core.project import ProjectFile
from pitloom.export.hashes import sha256_of
from pitloom.id_registry import AI_PACKAGE_TYPE, FILE_TYPE, IdRegistry
from pitloom.id_registry._ambiguous import harvest_sha256, unique_file_keys
from pitloom.id_registry._harvest import (
    _harvest_elements,
    _own_sha256,
    content_gate_message,
)
from tests._lfs import lfs_pointer_bytes
from tests.id_registry._registry_harvest_shared import (
    _CI,
    _NS,
    _file,
    _hash,
    _object_set,
)
from tests.id_registry.test_registry_lfs_pointer_order import _KEY, _Scene

_CONTENT = b"real content\n"
_OID = hashlib.sha256(_CONTENT).hexdigest()
_TEXT_SHA = hashlib.sha256(lfs_pointer_bytes(_CONTENT)).hexdigest()
_PLAIN_SHA = "c" * 64
_POINTER_ID, _PLAIN_ID, _UNHASHED_ID, _FRAGMENT_ID = (
    f"{_NS}#File-{n}" for n in (1, 2, 3, 9)
)
#: What a hook or wheel run records: each file's key, the pointer's oid.
_KEYS = {
    _POINTER_ID: (FILE_TYPE, _KEY),
    _PLAIN_ID: (FILE_TYPE, "demo/a.py"),
    _UNHASHED_ID: (FILE_TYPE, "demo/u.txt"),
}
_HASHES = {_POINTER_ID: _OID}


def _elements() -> dict[str, spdx3.software_File]:
    """An archive's pointer (states the text's digest), a plain and an
    unhashed file, and a merged loom fragment's element of the pointer (it
    states the ``oid``, and has no recorded key)."""
    return {
        "pointer": _file(_KEY, _POINTER_ID, _TEXT_SHA),
        "plain": _file("demo/a.py", _PLAIN_ID, _PLAIN_SHA),
        "unhashed": _file("demo/u.txt", _UNHASHED_ID),
        "fragment": _file(_KEY, _FRAGMENT_ID, _OID),
    }


_EXPECTED = {"pointer": _OID, "plain": _PLAIN_SHA, "unhashed": None, "fragment": _OID}


@pytest.mark.parametrize("kind", _EXPECTED)
def test_the_harvest_readers_agree_on_each_file(kind: str) -> None:
    obj = _elements()[kind]
    expected = _EXPECTED[kind]
    assert harvest_sha256(obj, _HASHES) == expected
    assert _own_sha256(obj, FILE_TYPE, imported=False, hashes=_HASHES) == expected
    keyed = {} if expected is None else {expected: str(obj.name)}
    assert unique_file_keys([obj], _KEYS, _HASHES) == keyed
    # Only a recorded pointer reads another hash than the one it states.
    assert (harvest_sha256(obj, None) == expected) is (kind != "pointer")


def test_a_recorded_hash_applies_to_a_file_only() -> None:
    package = spdx3.software_Package(spdxId=_POINTER_ID, name="demo", creationInfo=_CI)
    package.verifiedUsing = _hash(_TEXT_SHA)
    assert harvest_sha256(package, _HASHES) == _TEXT_SHA == sha256_of(package)


_OTHER_PTR_ID = f"{_NS}#File-4"
_OTHER_KEY = "demo/b.bin"


def _twin_case(case: str) -> tuple[list[spdx3.software_File], dict[str, str]]:
    """The run's pointer (states the text's digest) and a merged fragment's
    element of its path (*case*: ``oid`` its twin; ``other`` a pointer
    replaced by other content; ``unhashed`` no hash; ``plain`` the run's
    file is no pointer, stating the fragment's hash, a pointer at another
    path; ``two-paths`` a second pointer of the one ``oid`` with its own
    twin); the hashes the run recorded."""
    pointer, hashes = _elements()["pointer"], dict(_HASHES)
    twin_sha: str | None = {"other": "d" * 64, "unhashed": None}.get(case, _OID)
    if case == "plain":
        pointer, twin_sha = _file(_KEY, _POINTER_ID, _PLAIN_SHA), _PLAIN_SHA
        hashes = {}
    objects = [pointer, _file(_KEY, _FRAGMENT_ID, twin_sha)]
    if case in ("plain", "two-paths"):
        hashes[_OTHER_PTR_ID] = _OID
        objects.append(_file(_OTHER_KEY, _OTHER_PTR_ID, _TEXT_SHA))
    if case == "two-paths":
        objects.append(_file(_OTHER_KEY, f"{_NS}#File-8", _OID))
    return objects, hashes


#: Per case: the file entries harvest writes, and its ``INFO:`` lines.
_TWIN_WANT = {
    "oid": ({_KEY: (_POINTER_ID, _OID)}, []),
    "other": (
        {_KEY: (_POINTER_ID, _OID)},
        [
            content_gate_message(
                (FILE_TYPE, _KEY), _FRAGMENT_ID, _POINTER_ID, older=True
            )
        ],
    ),
    # Ambiguous, as any two elements of one path: content unknown, or no
    # pointer.
    "unhashed": ({}, []),
    "plain": ({_OTHER_KEY: (_OTHER_PTR_ID, _OID)}, []),
    "two-paths": (
        {_KEY: (_POINTER_ID, _OID), _OTHER_KEY: (_OTHER_PTR_ID, _OID)},
        [],
    ),
}


@pytest.mark.parametrize("reverse", [False, True], ids=["run-first", "twin-first"])
@pytest.mark.parametrize("case", _TWIN_WANT)
def test_a_fragment_twin_of_a_pointer_leaves_the_run_element_written(
    caplog: pytest.LogCaptureFixture, case: str, reverse: bool
) -> None:
    """A merged fragment's element stating a pointer's ``oid`` at its path
    is the run's own content: never written (its id reserved, no
    ``older SHA-256`` line), so the run's element is, with the ``oid``.
    Other content stays stale; a twin of a file that is no pointer, or of
    another path, changes nothing."""
    objects, hashes = _twin_case(case)
    keys = {
        str(o.spdxId): (FILE_TYPE, str(o.name))
        for o in objects
        if str(o.spdxId) in (_POINTER_ID, _OTHER_PTR_ID)
    }
    registry = IdRegistry.new("proj", namespace=_NS)
    caplog.set_level(logging.INFO, logger="pitloom.id_registry")
    order = objects[::-1] if reverse else objects
    _harvest_elements(registry, order, imported=False, keys=keys, hashes=hashes)
    entries, infos = _TWIN_WANT[case]
    assert {
        name: (e.spdx_id, e.sha256) for (_, name), e in registry.elements.items()
    } == entries
    assert [r.getMessage() for r in caplog.records] == infos
    assert registry.register(FILE_TYPE, "n") == f"{_NS}#File-10"  # 9 reserved


@pytest.mark.parametrize("twin", [False, True], ids=["alone", "with-twin"])
def test_a_fragment_model_of_a_pointer_is_keyed_by_its_file(twin: bool) -> None:
    """A merged fragment's model of a pointer's ``oid`` is written under the
    pointer's key, a twin of the pointer beside it or not (the two are one
    file, not two holding the SHA-256)."""
    model = spdx3.ai_AIPackage(spdxId=f"{_NS}#AIPackage-9", name="m", creationInfo=_CI)
    model.verifiedUsing = _hash(_OID)
    objects = [_elements()["pointer"], model]
    if twin:
        objects.append(_file(_KEY, _FRAGMENT_ID, _OID))
    registry = IdRegistry.new("proj", namespace=_NS)
    registry.harvest(_object_set(*objects), keys=_KEYS, hashes=_HASHES)
    entry = registry.get(AI_PACKAGE_TYPE, _KEY)
    assert entry and entry.spdx_id == f"{_NS}#AIPackage-9" and entry.sha256 == _OID


@pytest.mark.parametrize(
    ("hashes", "recorded"), [(_HASHES, _OID), ({}, _TEXT_SHA)], ids=["oid", "none"]
)
def test_harvest_records_the_hash_the_run_gated_on(
    hashes: dict[str, str], recorded: str
) -> None:
    elements = _elements()
    registry = IdRegistry.new("proj", namespace=_NS)
    registry.harvest(
        _object_set(elements["pointer"], elements["plain"]), keys=_KEYS, hashes=hashes
    )
    pointer, plain = (registry.get(FILE_TYPE, n) for n in (_KEY, "demo/a.py"))
    assert pointer and pointer.spdx_id == _POINTER_ID and pointer.sha256 == recorded
    assert plain and plain.sha256 == _PLAIN_SHA


def _base_plumbing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Put back the stated-hash rule: lookups gate on ``digest_sha256``
    and every harvest reader takes ``sha256_of``."""
    monkeypatch.setattr(ProjectFile, "registry_sha256", lambda pf: pf.digest_sha256)
    for module in ("_ambiguous", "_harvest"):
        monkeypatch.setattr(
            f"pitloom.id_registry.{module}.harvest_sha256",
            lambda obj, _hashes: sha256_of(obj),
        )


def _outputs(base: Path, mp: pytest.MonkeyPatch, data: bytes) -> list[str | None]:
    """Each step's SBOM and the registry after it."""
    tree = {"demo/__init__.py": b"x = 1\n", _KEY: data}
    scene = _Scene(base, mp, tree)
    out: list[str | None] = []
    for step in ("idgen", "wheel", "checkout", "sdist", "built", "checkout", "hook"):
        out += [scene.run(step), scene.reg.read_text(encoding="utf-8")]
    return out


@pytest.mark.usefixtures("fixed_epoch")
@pytest.mark.parametrize(
    ("data", "same"),
    [(b"plain bytes\n", True), (lfs_pointer_bytes(_CONTENT), False)],
    ids=["no-pointer", "pointer"],
)
def test_a_project_without_pointers_is_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, data: bytes, same: bool
) -> None:
    """Every route's SBOM and registry bytes equal those of the stated-hash
    rule for a project with no pointer; with one they differ (the patch is
    not vacuous)."""
    now = _outputs(tmp_path / "now", monkeypatch, data)
    with monkeypatch.context() as patched:
        _base_plumbing(patched)
        before = _outputs(tmp_path / "before", patched, data)
    assert (now == before) is same
