# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``IdRegistry.generate``: layout-alias promotion, keys of two spellings
of one name, and the project prefix.

See also: test_registry_promote_alias.py (the promotion itself),
test_registry_generate.py and test_registry_generate_paths.py (the rest of
the indexing), test_keys.py (the key helpers).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

import pytest

import pitloom.id_registry._generate as ids_mod
from pitloom.id_registry import AI_PACKAGE_TYPE, FILE_TYPE, IdRegistry, keys
from pitloom.id_registry._types import _iter_files
from pitloom.id_registry.import_keys import LAYOUT_ALIAS_CHANGED_INFO
from tests.id_registry.shared import _files
from tests.registry_helpers import make_registry

_NS = "https://spdx.org/spdxdocs/proj-1"
_BYTES = b"print('x')\n"
_NEW = b"print('y')\n"
_NFD = "café"
_NFC = "café"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _project(root: Path, *files: str, data: bytes = _BYTES) -> Path:
    for name in files:
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(data)
    return root


def _registry(*held: tuple[str, bytes], type_name: str = FILE_TYPE) -> IdRegistry:
    registry = IdRegistry.new("proj")
    for key, data in held:
        registry.register(type_name, key, sha256=_sha(data))
    return registry


def _ids(registry: IdRegistry) -> dict[str, str]:
    return {name: entry.spdx_id for name, entry in _files(registry).items()}


def _promoted(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if "promoted from" in r.message]


@pytest.mark.parametrize("root", ["src", "lib"])
def test_generate_moves_the_one_held_alias_to_the_new_key(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, root: str
) -> None:
    disk = f"{root}/demo/x.py"
    project = _project(tmp_path, disk)
    registry = _registry(("demo/x.py", _BYTES))
    before = _ids(registry)["demo/x.py"]
    counters = dict(registry.id_counters)

    with caplog.at_level(logging.INFO, logger="pitloom"):
        registry.generate([project], project)

    assert _ids(registry) == {disk: before}
    assert registry.id_counters == counters
    assert _promoted(caplog) == ["ID registry: 1 key(s) promoted from a layout alias"]


@pytest.mark.parametrize(
    ("alias", "real", "moved"),
    [(_NEW, False, True), (_BYTES, False, False), (_NEW, True, False)],
    ids=["new-bytes", "old-bytes", "real-file"],
)
# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def test_generate_moves_the_alias_holding_the_new_bytes_over_a_changed_key(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    alias: bytes,
    real: bool,
    moved: bool,
) -> None:
    """``src/demo/x.py`` held for its old bytes, its wheel path
    ``demo/x.py`` for the edited ones (a wheel run before ``id generate``):
    the alias's id replaces the changed key's, as a project run's lookup
    hits it, so project and wheel keep one id. The replaced id is never
    minted again. Not for an alias of other bytes, nor a real file."""
    project = _project(tmp_path, "src/demo/x.py", data=_NEW)
    if real:
        _project(tmp_path, "demo/x.py", data=_NEW)
    old, wheel = f"{_NS}#File-9", f"{_NS}#File-2"
    held = {"src/demo/x.py": (old, _sha(_BYTES)), "demo/x.py": (wheel, _sha(alias))}
    entries = {(FILE_TYPE, k): v for k, v in held.items()}
    registry = make_registry(entries, namespace=_NS, project_root=project)
    registry.id_counters["File"] = 8

    with caplog.at_level(logging.INFO, logger="pitloom"):
        registry.generate([project / "src"], project)

    ids = _ids(registry)
    assert (ids["src/demo/x.py"] == wheel) is moved
    assert ("demo/x.py" not in ids) is moved
    assert old not in (*ids.values(), registry.register(FILE_TYPE, "n", sha256=None))
    said = [m for m in caplog.messages if "changed" in m]
    assert len(said) == 1 and (said[0] == LAYOUT_ALIAS_CHANGED_INFO % 1) is moved


@pytest.mark.parametrize("real", [True, False], ids=["real-file", "no-file"])
def test_generate_never_moves_a_canonical_key_to_a_shorter_one(
    tmp_path: Path, real: bool
) -> None:
    """``src/demo/x.py`` held, then ``id generate demo/`` on a real
    root-level ``demo/x.py`` of the same bytes: the held key stays."""
    project = _project(tmp_path, "src/demo/x.py", "demo/x.py")
    registry = _registry()
    registry.generate([project / "src"], project)
    held = _ids(registry)
    if not real:
        (project / "src" / "demo" / "x.py").unlink()

    registry.generate([project / "demo"], project)

    ids = _ids(registry)
    assert ids["src/demo/x.py"] == held["src/demo/x.py"]
    assert ids["demo/x.py"] != held["src/demo/x.py"]


def test_generate_never_moves_a_longer_alias(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``lib/src/demo/x.py`` held: ``src/demo/x.py`` is its layout alias,
    the shorter key, so it is not moved there, even when the walked key
    names no file as spelt (an NFD name on disk keyed NFC)."""
    _clash_walk(monkeypatch, tmp_path, "src/demo/x.py")
    registry = IdRegistry.new("proj")
    held = registry.register(FILE_TYPE, "lib/src/demo/x.py", sha256=_sha(b"x.py"))

    registry.generate([tmp_path], tmp_path)

    ids = _ids(registry)
    assert ids["lib/src/demo/x.py"] == held != ids["src/demo/x.py"]


def test_generate_never_takes_the_id_of_a_real_shorter_file(tmp_path: Path) -> None:
    """``demo/x.py`` held for a real file, then ``id generate src/`` on
    ``src/demo/x.py`` of the same bytes: two files, two ids."""
    project = _project(tmp_path, "src/demo/x.py", "demo/x.py")
    registry = _registry()
    registry.generate([project / "demo"], project)
    held = _ids(registry)["demo/x.py"]

    registry.generate([project / "src"], project)

    ids = _ids(registry)
    assert ids["demo/x.py"] == held != ids["src/demo/x.py"]


def test_generate_checks_real_files_below_a_project_outside_the_root(
    tmp_path: Path,
) -> None:
    """A project outside the registry's root keys its files from the
    project: the real shorter file is looked for there."""
    project = _project(tmp_path / "proj", "src/demo/x.py", "demo/x.py")
    registry = IdRegistry.new("x", project_root=tmp_path / "elsewhere")
    held = registry.register(FILE_TYPE, "demo/x.py", sha256=_sha(_BYTES))

    registry.generate([project / "src"], project)

    ids = _ids(registry)
    assert ids["demo/x.py"] == held != ids["src/demo/x.py"]


def test_a_promotion_adds_no_id_to_the_saved_registry(tmp_path: Path) -> None:
    root = _project(tmp_path / "proj", "src/demo/x.py")
    path = tmp_path / "proj" / "ids.json"
    registry = _registry(("demo/x.py", _BYTES))
    registry.save(path)
    registry = IdRegistry.load(path)

    registry.generate([root / "src"], root)
    rebase = registry.rebase()

    assert list(_files(registry)) == ["src/demo/x.py"]
    assert rebase.added == 0 and rebase.refused == 0


def test_generate_moves_nothing_for_other_bytes(tmp_path: Path) -> None:
    root = _project(tmp_path, "src/demo/x.py")
    registry = _registry(("demo/x.py", b"other\n"))
    old = _ids(registry)["demo/x.py"]

    registry.generate([root], root)

    ids = _ids(registry)
    assert set(ids) == {"demo/x.py", "src/demo/x.py"}
    assert ids["demo/x.py"] == old != ids["src/demo/x.py"]


def test_generate_moves_nothing_of_another_type(tmp_path: Path) -> None:
    root = _project(tmp_path, "src/demo/x.py")
    registry = _registry(("demo/x.py", _BYTES), type_name=AI_PACKAGE_TYPE)

    registry.generate([root], root)

    assert list(_files(registry)) == ["src/demo/x.py"]
    assert (AI_PACKAGE_TYPE, "demo/x.py") in registry.elements


def test_generate_keeps_a_held_new_key_and_its_aliases(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A held key is no new key: no move and no tie message, however many
    aliases it has."""
    root = _project(tmp_path, "src/demo/x.py")
    registry = _registry(
        ("demo/x.py", _BYTES), ("src/demo/x.py", _BYTES), ("v/src/demo/x.py", _BYTES)
    )
    before = _ids(registry)

    with caplog.at_level(logging.INFO, logger="pitloom"):
        registry.generate([root], root)

    assert _ids(registry) == before and len(set(before.values())) == 3
    assert not caplog.records


def test_generate_does_not_move_the_alias_of_a_file_on_disk(tmp_path: Path) -> None:
    """Both files exist: the alias is a file of its own, not the old name
    of the other."""
    root = _project(tmp_path, "demo/x.py", "src/demo/x.py")
    registry = _registry(("demo/x.py", _BYTES))
    old = _ids(registry)["demo/x.py"]

    registry.generate([root], root)

    ids = _ids(registry)
    assert ids["demo/x.py"] == old
    assert ids["src/demo/x.py"] != old


def test_generate_moves_only_a_src_or_lib_alias(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """``tests/demo/x.py`` is a file of its own, never the alias of
    ``demo/x.py``; nor is ``v/src/demo/x.py`` that of ``src/demo/x.py``."""
    project = _project(tmp_path, "tests/demo/x.py", "src/demo/x.py")
    registry = _registry(("demo/x.py", _BYTES), ("v/src/demo/x.py", _BYTES))
    before = _ids(registry)

    with caplog.at_level(logging.INFO, logger="pitloom"):
        registry.generate([project / "tests"], project)
        assert _ids(registry)["demo/x.py"] == before["demo/x.py"]
        registry.generate([project / "src"], project)

    ids = _ids(registry)
    assert ids["src/demo/x.py"] == before["demo/x.py"]
    assert ids["v/src/demo/x.py"] == before["v/src/demo/x.py"]
    assert ids["tests/demo/x.py"] not in before.values()
    assert _promoted(caplog) == ["ID registry: 1 key(s) promoted from a layout alias"]


def test_generate_keys_a_file_named_twice_once(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    root = _project(tmp_path, "d/a.txt")
    spellings = [Path("d/a.txt"), Path("d/../d/a.txt")]
    registry = IdRegistry.new("proj")

    assert len(list(_iter_files(spellings, root))) == 2  # not vacuous
    with caplog.at_level(logging.INFO, logger="pitloom"):
        registry.generate(spellings, root)

    assert list(_files(registry)) == ["d/a.txt"]
    assert not caplog.records


def _clash_walk(monkeypatch: pytest.MonkeyPatch, root: Path, *names: str) -> list[Path]:
    """Walk *names* below *root* as if each were a file with its own bytes
    (the names need not exist)."""
    files = [root / name for name in names]
    monkeypatch.setattr(ids_mod, "_iter_files", lambda *_a, **_k: iter(files))
    monkeypatch.setattr(ids_mod, "sha256_file", lambda p: _sha(p.name.encode()))
    return files


@pytest.mark.parametrize("fake", [False, True], ids=["on-disk", "patched-walk"])
def test_generate_skips_both_files_of_one_nfc_key_with_one_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    fake: bool,
) -> None:
    root = _project(tmp_path, "keep.txt")
    spellings = [f"data/{_NFD}.txt", f"data/{_NFC}.txt"]
    if fake:
        _clash_walk(monkeypatch, root, "keep.txt", *spellings)
    else:
        (root / "data").mkdir()
        for name in spellings:
            (root / name).write_bytes(name.encode())
        if len(os.listdir(root / "data")) != 2:
            pytest.skip("the file system folds the two spellings")
    registry = IdRegistry.new("proj")

    with caplog.at_level(logging.INFO, logger="pitloom"):
        registry.generate([root], root)

    assert list(_files(registry)) == ["keep.txt"]
    assert registry.id_counters == {"File": 1}  # nothing minted for the twins
    (warning,) = caplog.records
    assert warning.levelno == logging.WARNING
    assert warning.getMessage().startswith("ID registry: 2 files have one key")
    assert f"data/{_NFC}.txt" in warning.getMessage()


def test_generate_skipping_a_clash_leaves_held_ids_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Neither twin is registered, so no run re-mints the other's id."""
    root = _project(tmp_path)
    _clash_walk(monkeypatch, root, f"{_NFD}.txt", f"{_NFC}.txt")
    registry = IdRegistry.new("proj")
    held = registry.register(FILE_TYPE, f"{_NFC}.txt", sha256=_sha(b"old"))

    for _ in range(2):
        registry.generate([root], root)

    assert _ids(registry) == {f"{_NFC}.txt": held}


def test_generate_prefixes_keys_with_the_project_below_the_registry_root(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path / "mono" / "pkg", "src/a.py")
    registry = IdRegistry.new("mono", project_root=tmp_path / "mono")

    registry.generate([project], project)

    assert list(_files(registry)) == ["pkg/src/a.py"]


def test_generate_keeps_project_keys_for_a_project_outside_the_root(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path / "proj", "src/a.py")
    registry = IdRegistry.new("x", project_root=tmp_path / "elsewhere")

    registry.generate([project], project)

    assert list(_files(registry)) == ["src/a.py"]


def test_generate_keys_a_project_typed_in_another_case_as_listed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The project prefix takes the spelling the directory lists (a
    case-insensitive file system), the walked names stay as walked."""
    mono = tmp_path / "mono"
    (mono / "pkg").mkdir(parents=True)
    typed = mono / "PKG"
    _clash_walk(monkeypatch, typed, "src/a.py")
    monkeypatch.setattr(keys, "_listdir", lambda _directory: ["pkg"])
    monkeypatch.setattr(keys, "file_id", lambda _path: (1, 1))
    registry = IdRegistry.new("mono", project_root=mono)

    registry.generate([typed], typed)

    assert list(_files(registry)) == ["pkg/src/a.py"]
