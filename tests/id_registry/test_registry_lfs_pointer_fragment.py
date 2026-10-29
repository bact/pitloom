# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A merged loom fragment that states a Git LFS pointer's ``oid`` does not
cost the pointer its id: an ``--allow-build`` run's SBOM states the pointer
text's digest, so the merge keeps two elements of one path (a known limit),
yet harvest records the run's own element with the ``oid``, and a later
checkout keeps that id. A project with no pointer is unchanged.

See also: test_registry_lfs_pointer_order.py (the route-and-order matrix
this extends), test_registry_lfs_pointer_harvest.py (the harvest rule).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pitloom import loom
from tests.id_registry.test_registry_lfs_pointer_order import (
    _INIT,
    _KEY,
    _OID,
    _STEPS,
    _TEXT_SHA,
    _Scene,
)

pytestmark = pytest.mark.usefixtures("fixed_epoch")

_FRAGMENT = "frag.json"


def _write_fragment(scene: _Scene, *, registry: bool) -> None:
    """``loom.add_dataset`` of the pointer, the run in the project (with
    the project's registry when *registry*)."""
    with pytest.MonkeyPatch.context() as mp:
        mp.chdir(scene.root)
        mp.setattr("pitloom._loom_active_run._get_caller_script_path", lambda: None)
        with loom.run(
            scene.root / _FRAGMENT, id_registry=scene.reg if registry else None
        ):
            loom.add_dataset(_KEY)


def _scene(base: Path, mp: pytest.MonkeyPatch, data: bytes | None = None) -> _Scene:
    """A :class:`_Scene` (its pointer, or *data* at the path) whose
    ``pyproject.toml`` merges a loom fragment of it."""
    tree = None if data is None else {"demo/__init__.py": _INIT, _KEY: data}
    scene = _Scene(base, mp, tree)
    _write_fragment(scene, registry=False)
    with (scene.root / "pyproject.toml").open("ab") as handle:
        handle.write(f'[tool.pitloom.fragment]\nfiles = ["{_FRAGMENT}"]\n'.encode())
    return scene


def _file_ids(sbom: str) -> dict[str, str]:
    """spdxId -> the SHA-256 stated, of each element of the pointer."""
    return {
        n["spdxId"]: n["verifiedUsing"][0]["hashValue"]
        for n in json.loads(sbom)["@graph"]
        if n.get("type") == "software_File" and n.get("name") == _KEY
    }


@pytest.mark.parametrize(
    "sequence",
    [
        "built,built,checkout",
        "wheel,checkout",
        "checkout,built,checkout",
        "checkout,loom,built,built,checkout",
        "built,loom,checkout,built",
    ],
)
def test_a_fragment_of_a_pointer_keeps_one_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sequence: str
) -> None:
    """``loom``: the fragment is run again with the project's registry.
    Each run's own element of the pointer has the id the registry then
    holds, with the ``oid``; a built run also keeps the fragment's element
    (two elements, the known limit), a checkout run folds it."""
    scene = _scene(tmp_path, monkeypatch)
    ids = set()
    for step in sequence.split(","):
        if step == "loom":
            _write_fragment(scene, registry=True)
            continue
        found = _file_ids(scene.run(step) or "")
        # A checkout states the oid, an archive the text's digest; only a
        # built run merges the fragment (the oid) as a second element.
        own_sha = _OID if step == "checkout" else _TEXT_SHA
        extra = [_OID] if step == "built" else []
        assert sorted(found.values()) == sorted([own_sha, *extra]), step
        (own,) = (i for i, sha in found.items() if sha == own_sha)
        assert scene.held() == (own, _OID), step
        ids.add(own)
    assert len(ids) == 1, ids


def _outputs(scene: _Scene, steps: list[str]) -> list[str | None]:
    out: list[str | None] = []
    for step in steps:
        out += [_STEPS[step](scene), scene.reg.read_text(encoding="utf-8")]
    return out


_PLAIN = b"plain bytes\n"


@pytest.mark.parametrize(
    ("data", "sequence", "same"),
    [
        (_PLAIN, "built,built,checkout", True),
        (_PLAIN, "wheel,checkout", True),
        (_PLAIN, "checkout,built,checkout", True),
        (None, "built,built,checkout", False),
    ],
    ids=["plain-built", "plain-wheel", "plain-checkout", "pointer-built"],
)
def test_a_fragment_of_a_file_that_is_no_pointer_is_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    data: bytes | None,
    sequence: str,
    same: bool,
) -> None:
    """Each step's SBOM and registry bytes equal those with the pointer
    rule switched off for a project with no pointer, the fragment the same
    bytes; with a pointer they differ (the switch is not vacuous)."""
    now = _scene(tmp_path / "now", monkeypatch, data)
    fragment = (now.root / _FRAGMENT).read_bytes()
    before = _scene(tmp_path / "before", monkeypatch, data)
    (before.root / _FRAGMENT).write_bytes(fragment)
    steps = sequence.split(",")
    with monkeypatch.context() as patched:
        for module in ("_ambiguous", "_harvest"):
            patched.setattr(
                f"pitloom.id_registry.{module}.pointer_twins", lambda *_: {}
            )
        old = _outputs(before, steps)
    assert (_outputs(now, steps) == old) is same
