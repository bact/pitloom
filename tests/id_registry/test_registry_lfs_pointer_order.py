# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The order of runs never changes a Git LFS pointer's id: the registry
holds the pointer's ``oid`` after every run that writes it (checkout,
wheel, sdist, ``--allow-build``, ``id generate``, ``id import``), though an
archive's SBOM states the digest of the pointer text. Plus the adversarial
rows: files alike by bytes, a replaced pointer, look-alikes, determinism.

See also: tests/id_registry/test_registry_lfs_pointer.py (the checkout),
test_registry_lfs_pointer_routes.py (the routes on a checkout registry).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple

import pytest

from pitloom.assemble import generate_project_sbom, generate_wheel_sbom
from pitloom.core.build_options import BuildOptions
from pitloom.id_registry import FILE_TYPE, IdRegistry, RegistryEntry
from pitloom.id_registry._format import write_registry_file
from tests._lfs import lfs_pointer_bytes, write_project
from tests._wheel_models import write_model_wheel
from tests.build_and_read_shared import install_fake_build
from tests.id_registry.test_registry_lfs_pointer_routes import (
    _ROUTES,
    _ids,
)

pytestmark = pytest.mark.usefixtures("fixed_epoch")

_CONTENT = b"real content\n"
_PTR = lfs_pointer_bytes(_CONTENT)
_OID = hashlib.sha256(_CONTENT).hexdigest()
_TEXT_SHA = hashlib.sha256(_PTR).hexdigest()
_INIT = b"x = 1\n"
_NAMESPACE = "https://example.org/spdxdocs/proj-1"
_KEY = "demo/data.bin"
_TREE = {"demo/__init__.py": _INIT, _KEY: _PTR}
_ROUTE_NAMES = ["checkout", "wheel", "sdist", "built", "hook"]
#: The steps that write the registry; ``hook`` reads it only.
_WRITERS = {"idgen", "checkout", "wheel", "sdist", "built", "import"}


class _Scene:
    """One project of *tree* with its registry, and the files each route
    reads (``put`` changes both the project and the archives' members)."""

    def __init__(
        self,
        base: Path,
        mp: pytest.MonkeyPatch,
        tree: dict[str, bytes] | None = None,
    ) -> None:
        self.base, self.mp = base, mp
        self.tree = dict(_TREE if tree is None else tree)
        self.root = write_project(base / "p", self.tree)
        with (self.root / "pyproject.toml").open("ab") as handle:
            handle.write(b'[tool.pitloom]\nid-registry = "ids.json"\n')
        self.reg = self.root / "ids.json"
        IdRegistry.new(
            "proj", self.reg, namespace=_NAMESPACE, project_root=self.root
        ).save(self.reg)

    def put(self, name: str, data: bytes) -> None:
        self.tree[name] = data
        (self.root / name).parent.mkdir(parents=True, exist_ok=True)
        (self.root / name).write_bytes(data)

    def entry(self, name: str = _KEY) -> RegistryEntry | None:
        return IdRegistry.load(self.reg).get(FILE_TYPE, name)

    def held(self, name: str = _KEY) -> tuple[str, str | None] | None:
        entry = self.entry(name)
        return None if entry is None else (entry.spdx_id, entry.sha256)

    def run(self, step: str) -> str | None:
        """Run *step*; its SBOM, which must not repeat an ``spdxId``."""
        sbom = _STEPS[step](self)
        if sbom is not None:
            found = [n["spdxId"] for n in json.loads(sbom)["@graph"] if "spdxId" in n]
            assert len(found) == len(set(found)), step
        return sbom


def _idgen(scene: _Scene) -> None:
    registry = IdRegistry.load(scene.reg)
    registry.generate([Path("demo")], scene.root)
    registry.save(scene.reg)


def _checkout(scene: _Scene) -> str:
    return generate_project_sbom(scene.root, id_registry=scene.reg)


def _built(scene: _Scene) -> str:
    """``--allow-build`` on a backend with no static file list, the build
    writing *tree* (its pointer as text)."""
    manifest = scene.root / "pyproject.toml"
    original = manifest.read_bytes()
    manifest.write_bytes(
        original.replace(
            b'requires = ["hatchling"]\nbuild-backend = "hatchling.build"',
            b'requires = ["uv_build"]\nbuild-backend = "uv_build"',
        )
    )
    install_fake_build(scene.mp).entries = dict(scene.tree)
    try:
        return generate_project_sbom(
            scene.root, id_registry=scene.reg, build_options=BuildOptions(allow=True)
        )
    finally:
        manifest.write_bytes(original)


def _import(scene: _Scene) -> None:
    """``id import`` of a checkout SBOM (it states the ``oid``)."""
    path = scene.base / "imported.spdx3.json"
    path.write_text(
        generate_project_sbom(scene.root, update_id_registry=False), encoding="utf-8"
    )
    registry = IdRegistry.load(scene.reg)
    registry.import_sbom(path)
    registry.save(scene.reg)


def _pull(scene: _Scene) -> None:
    """``git lfs pull``: the real content replaces the pointer."""
    before = (scene.root / _KEY).read_bytes()
    scene.put(_KEY, _CONTENT)
    assert (scene.root / _KEY).read_bytes() != before


def _route(name: str) -> Callable[[_Scene], str]:
    return lambda s: _ROUTES[name](s.root, s.base, s.tree)


_STEPS: dict[str, Callable[[_Scene], str | None]] = {
    "idgen": _idgen,
    "checkout": _checkout,
    "wheel": _route("wheel"),
    "sdist": _route("sdist"),
    "built": _built,
    "hook": _route("hook"),
    "import": _import,
    "pull": _pull,
}


class _Seen(NamedTuple):
    step: str
    sbom_id: str | None
    before: tuple[str, str | None] | None
    after: tuple[str, str | None] | None


def _play(scene: _Scene, steps: list[str]) -> list[_Seen]:
    """Run *steps*; what each one stated for the pointer, and the registry
    entry before and after it."""
    seen = []
    for step in steps:
        before = scene.held()
        sbom = scene.run(step)
        sbom_id = None if sbom is None else _ids(sbom, (_KEY,)).get(_KEY)
        seen.append(_Seen(step, sbom_id, before, scene.held()))
    return seen


_SEQUENCES = [
    "idgen,wheel,checkout",
    "idgen,sdist,checkout",
    "idgen,built,checkout",
    "wheel,checkout",
    "sdist,checkout",
    "built,checkout",
    "checkout,wheel,checkout",
    "checkout,wheel,checkout,wheel,checkout",
    "checkout,sdist,built,wheel,checkout",
    "idgen,wheel,idgen",
    "idgen,pull,wheel,checkout",
    "wheel,pull,checkout",
    "wheel,import,checkout",
    "idgen,hook,checkout",
    "checkout,hook,checkout",  # the hook only reads
    "wheel,hook,checkout",
]


@pytest.mark.parametrize("sequence", _SEQUENCES)
def test_one_pointer_keeps_one_id_in_any_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sequence: str
) -> None:
    seen = _play(_Scene(tmp_path, monkeypatch), sequence.split(","))
    ids = {s.sbom_id or (s.after and s.after[0]) for s in seen} - {None}
    assert len(ids) == 1, seen
    writes = [s for s in seen if s.step in _WRITERS]
    assert [s.after and s.after[1] for s in writes] == [_OID] * len(writes), seen
    for s in seen:
        assert s.sbom_id is None or s.sbom_id == (s.after and s.after[0]), seen
        assert s.step != "hook" or s.before == s.after, seen  # read-only


@pytest.mark.parametrize(
    "steps",
    [["checkout", "wheel"], ["wheel", "checkout"], ["sdist", "built", "checkout"]],
    ids=["checkout-wheel", "wheel-checkout", "sdist-built-checkout"],
)
def test_alternation_does_not_rewrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    steps: list[str],
) -> None:
    """Once two passes settled the registry, a third rewrites no file entry
    (a spy on the write: a byte comparison cannot see a rewrite). The
    ``Tool`` and ``SoftwareAgent`` entries flip between the project and the
    wheel routes on their own, so only file entries are compared."""
    scene = _Scene(tmp_path, monkeypatch)
    _play(scene, steps * 2)
    assert scene.held()
    changed: list[object] = []

    def spy(target: Path, namespace: str, elements: Any, *rest: Any) -> None:
        on_disk = IdRegistry.load(target).elements
        files = {k: v for k, v in elements.items() if k[0] == FILE_TYPE}
        if files != {k: v for k, v in on_disk.items() if k[0] == FILE_TYPE}:
            changed.append(files)
        write_registry_file(target, namespace, elements, *rest)

    monkeypatch.setattr("pitloom.id_registry._registry.write_registry_file", spy)
    _play(scene, steps)
    assert not changed


# Adversarial rows.


def _scene_of(
    tmp_path: Path, mp: pytest.MonkeyPatch, data: bytes, seeded: bool = True
) -> _Scene:
    scene = _Scene(tmp_path, mp, {"demo/__init__.py": _INIT, _KEY: data})
    if seeded:
        _idgen(scene)
    return scene


_TWINS = {
    "text-twin": ("demo/copy.bin", _PTR),  # the bytes of P's pointer text
    "content-twin": ("demo/real.bin", _CONTENT),  # a file of SHA-256 = P's oid
}


@pytest.mark.parametrize("route", _ROUTE_NAMES)
@pytest.mark.parametrize("seed", ["both", "pointer", "twin"])
@pytest.mark.parametrize("case", _TWINS)
def test_files_alike_by_bytes_keep_their_own_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str, seed: str, route: str
) -> None:
    """Keys are paths: a second file equal to P's text, or with P's ``oid``
    as its SHA-256, neither takes P's id nor gives its own away."""
    name, data = _TWINS[case]
    full = {**_TREE, name: data}
    seeded = {"both": (_KEY, name), "pointer": (_KEY,), "twin": (name,)}[seed]
    scene = _Scene(
        tmp_path,
        monkeypatch,
        {k: v for k, v in full.items() if k == "demo/__init__.py" or k in seeded},
    )
    _idgen(scene)
    held = {k: scene.held(k) for k in seeded}
    for key, value in full.items():
        scene.put(key, value)
    ids = _ids(scene.run(route) or "", tuple(full))
    assert len(ids) == 3 and len(set(ids.values())) == 3
    assert all(h and ids[k] == h[0] for k, h in held.items())


@pytest.mark.parametrize("route", _ROUTE_NAMES)
def test_a_different_pointer_at_the_same_path_is_a_new_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, route: str
) -> None:
    scene = _scene_of(tmp_path, monkeypatch, _PTR)
    old, init = scene.held(_KEY), scene.held("demo/__init__.py")
    assert old and init
    scene.put(_KEY, lfs_pointer_bytes(b"other content\n"))
    ids = _ids(scene.run(route) or "", (_KEY, "demo/__init__.py"))
    assert ids[_KEY] != old[0]
    assert ids["demo/__init__.py"] == init[0]


@pytest.mark.parametrize("route", _ROUTE_NAMES)
@pytest.mark.parametrize("eols", [("\n", "\r\n"), ("\r\n", "\n")], ids=["lf", "crlf"])
def test_the_line_ending_of_a_pointer_does_not_change_its_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, eols: tuple[str, str], route: str
) -> None:
    first, second = (lfs_pointer_bytes(_CONTENT, eol=e) for e in eols)
    assert first != second
    scene = _scene_of(tmp_path, monkeypatch, first)
    old = scene.held()
    scene.put(_KEY, second)
    assert old
    assert _ids(scene.run(route) or "", (_KEY,))[_KEY] == old[0]


_ODD = {
    "look-alike": b"version https://git-lfs.github.com/spec/v1\n" + b"x" * 1024,
    "malformed": b"version https://git-lfs.github.com/spec/v1\n"
    + b"oid sha256:"
    + b"a" * 63
    + b"\nsize 5\n",
}


@pytest.mark.parametrize("route", _ROUTE_NAMES)
@pytest.mark.parametrize("kind", _ODD)
def test_a_file_only_opening_like_a_pointer_is_an_ordinary_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str, route: str
) -> None:
    """Its id holds through two runs of any route, and the registry holds
    the digest of its own bytes."""
    scene = _scene_of(tmp_path, monkeypatch, _ODD[kind])
    seeded = scene.held()
    assert seeded and seeded[1] == hashlib.sha256(_ODD[kind]).hexdigest()
    for _ in range(2):
        assert _ids(scene.run(route) or "", (_KEY,))[_KEY] == seeded[0]
        assert scene.held() == seeded


_PAIRS = {
    "src-flat-pointer": (("src/demo/x.bin", _PTR), ("demo/x.bin", _PTR)),
    # `demo/x.bin` names a real file, so it is not the layout alias of
    # `src/demo/x.bin`.
    "src-flat-real": (("src/demo/x.bin", _PTR), ("demo/x.bin", _CONTENT)),
    "monorepo": (("pkgs/a/x.bin", _PTR), ("pkgs/b/x.bin", _PTR)),
}


@pytest.mark.parametrize("kind", _PAIRS)
def test_one_oid_at_two_paths_keeps_two_ids(tmp_path: Path, kind: str) -> None:
    pair = _PAIRS[kind]
    root = write_project(tmp_path, dict(pair))
    tops = sorted({Path(name).parts[0] for name, _ in pair})
    path = root / "ids.json"
    IdRegistry.new("proj", path, project_root=root).save(path)
    rounds = []
    for _ in range(2):
        registry = IdRegistry.load(path)
        registry.generate([Path(t) for t in tops], root)
        registry.save(path)
        held = [registry.get(FILE_TYPE, name) for name, _ in pair]
        assert all(held)
        rounds.append([(e.spdx_id, e.sha256) for e in held if e])
    assert rounds[0] == rounds[1]
    assert rounds[0][0][0] != rounds[0][1][0]
    assert rounds[0][0][1] == rounds[0][1][1] == _OID


@pytest.mark.parametrize("route", _ROUTE_NAMES)
def test_runs_in_two_directories_give_the_same_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, route: str
) -> None:
    """The creation time is pinned: the SBOM and the registry (but its
    project root) are equal."""
    out = []
    for where in ("a", "b"):
        scene = _Scene(tmp_path / where, monkeypatch)
        _idgen(scene)
        out.append((scene.run(route), scene.reg.read_text(encoding="utf-8")))
    assert out[0][0] and out[0] == out[1]


def test_an_imported_archive_sbom_is_kept_and_the_checkout_misses_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Known limit (alpha): an archive SBOM states the text's digest, and
    ``id import`` records what an SBOM states, so the entry holds it; the
    next checkout run is a miss for the pointer alone (a new id, the entry
    now the ``oid``), and the one after holds."""
    scene = _Scene(tmp_path, monkeypatch)
    wheel = write_model_wheel(tmp_path / "dist", scene.tree)
    path = tmp_path / "wheel.spdx3.json"
    path.write_text(generate_wheel_sbom(wheel), encoding="utf-8")
    registry = IdRegistry.load(scene.reg)
    registry.import_sbom(path)
    registry.save(scene.reg)
    imported, init = scene.held(), scene.held("demo/__init__.py")
    assert imported and init and imported[1] == _TEXT_SHA != _OID
    ids = [_ids(scene.run("checkout") or "") for _ in range(3)]
    assert ids[0]["demo/__init__.py"] == init[0]
    assert ids[0][_KEY] != imported[0]
    assert ids[1] == ids[2] == ids[0]
    held = scene.held()
    assert held and held[0] == ids[0][_KEY] and held[1] == _OID
