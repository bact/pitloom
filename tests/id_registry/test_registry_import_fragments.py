# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``id import`` keys a file through its held layout alias, and a loom
fragment's dataset package and model as the next run looks them up; each
``INFO:`` says what was written.

See also: test_registry_import_keys.py (dataset and model keys of one
SBOM), tests/id_registry/_registry_harvest_shared.py (helpers).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom import loom
from pitloom.id_registry import (
    AI_PACKAGE_TYPE,
    DATASET_PACKAGE_TYPE,
    FILE_TYPE,
    IdRegistry,
)
from pitloom.id_registry.import_keys import (
    FILE_ALIAS_OVER_CHANGED_INFO,
    IMPORT_NOT_FOUND,
)
from tests.id_registry._registry_harvest_shared import _SHA_A, _SHA_B, _hash
from tests.id_registry.surfaces_base import _run_cli
from tests.registry_helpers import entries_of, make_registry

_NS = "https://spdx.org/spdxdocs/imported-1"
_ALIAS = "ID registry: 1 element(s) matched a registry key through the src/lib"
#: Serialisable: ``createdBy`` is required.
_CI = spdx3.CreationInfo(
    specVersion="3.0.1",
    created=datetime(2026, 1, 1, tzinfo=timezone.utc),
    createdBy=[f"{_NS}#SoftwareAgent-1"],
)


def _element(cls: Any, name: str, spdx_id: str, sha256: str) -> Any:
    obj = cls(spdxId=spdx_id, name=name, creationInfo=_CI)
    obj.verifiedUsing = _hash(sha256)
    return obj


def _write(path: Path, *objects: Any) -> Path:
    object_set = spdx3.SHACLObjectSet()
    for obj in objects:
        object_set.add(obj)
    with open(path, "wb") as f:
        spdx3.JSONLDSerializer().write(object_set, f)
    return path


def _infos(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [m for m in caplog.messages if m.startswith("ID registry: ")]


# --- files: the held layout alias -----------------------------------------


@pytest.mark.parametrize(
    ("held", "on_disk", "want"),
    [
        ({"src/demo/x.py": _SHA_A}, False, "src/demo/x.py"),
        ({"src/demo/x.py": _SHA_A}, True, "demo/x.py"),
        ({"src/demo/x.py": _SHA_B}, False, "demo/x.py"),
        ({"src/demo/x.py": _SHA_A, "lib/demo/x.py": _SHA_A}, False, "demo/x.py"),
        ({"pkgs/demo/src/demo/x.py": _SHA_A}, False, "demo/x.py"),
        ({"src/demo/x.py": _SHA_A, "demo/x.py": _SHA_A}, False, "demo/x.py"),
    ],
    ids=["alias", "real-file", "other-sha", "tie", "monorepo", "name-held"],
)
def test_import_keys_a_file_by_its_one_held_alias(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    held: dict[str, str],
    on_disk: bool,
    want: str,
) -> None:
    """A wheel SBOM's ``demo/x.py`` is written under the one held
    ``src/``/``lib/`` key with its SHA-256 (one id, one key, one INFO);
    otherwise, as before, under its name."""
    if on_disk:
        (tmp_path / "demo").mkdir()
        (tmp_path / "demo" / "x.py").write_bytes(b"")
    registry = make_registry(
        {
            (FILE_TYPE, k): (f"{_NS}#Old-{n}", s)
            for n, (k, s) in enumerate(held.items())
        },
        project_root=tmp_path,
    )
    file = _element(spdx3.software_File, "demo/x.py", f"{_NS}#File-1", _SHA_A)
    caplog.set_level(logging.INFO, logger="pitloom")

    registry.import_sbom(_write(tmp_path / "s.json", file))

    entry = registry.get(FILE_TYPE, want)
    assert entry is not None and entry.spdx_id == str(file.spdxId)
    ids = [e.spdx_id for e in registry.elements.values()]
    assert ids.count(str(file.spdxId)) == 1
    aliased = want != "demo/x.py"
    assert [m for m in _infos(caplog) if m.startswith(_ALIAS)] == (
        [f"{_ALIAS} layout alias"] if aliased else []
    )
    assert not [m for m in _infos(caplog) if "other content" in m]


@pytest.mark.parametrize(
    ("name", "alias", "on_disk", "want"),
    [
        ("demo/x.py", "src/demo/x.py", False, "src/demo/x.py"),
        ("src/demo/x.py", "demo/x.py", False, "demo/x.py"),
        ("demo/x.py", "src/demo/x.py", True, "demo/x.py"),
    ],
    ids=["wheel-name", "project-name", "real-file"],
)
# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def test_import_keys_a_changed_file_by_the_alias_holding_its_bytes(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    name: str,
    alias: str,
    on_disk: bool,
    want: str,
) -> None:
    """The imported file's own key holds other bytes, its one layout alias
    the imported ones: written under the alias, as a run's lookup finds
    it, so the file keeps one id (one INFO); the own key keeps its entry.
    Not when the shorter key is a real file."""
    if on_disk:
        (tmp_path / "demo").mkdir()
        (tmp_path / "demo" / "x.py").write_bytes(b"")
    own = (f"{_NS}#Old-1", _SHA_B)
    held = {(FILE_TYPE, name): own, (FILE_TYPE, alias): (f"{_NS}#Old-2", _SHA_A)}
    registry = make_registry(held, project_root=tmp_path)
    file = _element(spdx3.software_File, name, f"{_NS}#File-1", _SHA_A)
    caplog.set_level(logging.INFO, logger="pitloom")

    registry.import_sbom(_write(tmp_path / "s.json", file))

    entries = entries_of(registry)
    assert entries[(FILE_TYPE, want)] == (str(file.spdxId), _SHA_A)
    aliased = want != name
    assert (entries[(FILE_TYPE, name)] == own) is aliased
    said = [m for m in _infos(caplog) if m.startswith(_ALIAS)]
    over = [FILE_ALIAS_OVER_CHANGED_INFO % 1] if aliased else []
    assert [m for m in _infos(caplog) if "other content" in m] == over
    assert said == ([f"{_ALIAS} layout alias"] if aliased else [])


@pytest.mark.parametrize("edited", [False, True], ids=["r4", "edited"])
def test_project_sbom_imported_after_id_generate_keeps_one_key_per_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, edited: bool
) -> None:
    """The R4 repro: a project SBOM made with no registry, then ``id
    generate src`` and ``id import``: one key per file, so the next project
    run and the wheel agree on each file's id. Also ``id generate``, an
    edit, the SBOM, ``id import`` and ``id generate`` again: the imported
    alias of the edited bytes takes over the changed key."""
    project = tmp_path / "proj"
    (project / "src" / "demo").mkdir(parents=True)
    (project / "src" / "demo" / "__init__.py").write_bytes(b"")
    (project / "src" / "demo" / "x.py").write_bytes(b"x = 1\n")
    (project / "pyproject.toml").write_bytes(
        b'[build-system]\nrequires = ["hatchling"]\nbuild-backend = "hatchling.build"\n'
        b'[project]\nname = "demo"\nversion = "1.0.0"\n'
        b'[tool.hatch.build.targets.wheel]\npackages = ["src/demo"]\n'
    )
    old, reg = tmp_path / "old.json", project / "reg.json"
    sbom = ["project", str(project), "-o", str(old)]
    generate = ["id", "generate", "src", "-o", str(reg)]
    monkeypatch.chdir(project)
    if edited:
        assert _run_cli(monkeypatch, generate) == 0
        (project / "src" / "demo" / "x.py").write_bytes(b"x = 2\n")
    assert _run_cli(monkeypatch, sbom) == 0
    steps = [["id", "import", str(old), "-o", str(reg)], generate]
    for argv in steps if edited else steps[::-1]:
        assert _run_cli(monkeypatch, argv) == 0

    files = {
        k[1]: e.spdx_id
        for k, e in IdRegistry.load(reg).elements.items()
        if k[0] == FILE_TYPE and e.sha256 is not None
    }
    assert sorted(files) == ["src/demo/__init__.py", "src/demo/x.py"]
    graph = json.loads(old.read_text(encoding="utf-8"))["@graph"]
    imported = {e["name"]: e["spdxId"] for e in graph if e["type"] == FILE_TYPE}
    assert files["src/demo/x.py"] == imported["demo/x.py"]


# --- a loom fragment's dataset package and model --------------------------


@pytest.fixture(name="project")
def _project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A project holding ``data/t.txt`` and ``models/m.bin``, its scripts
    in ``scripts/``, the current directory."""
    root = tmp_path / "proj"
    for name, data in (("data/t.txt", b"rows\n"), ("models/m.bin", b"weights")):
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(data)
    (root / "scripts").mkdir()
    monkeypatch.chdir(root / "scripts")
    monkeypatch.setattr(
        "pitloom._loom_active_run._get_caller_script_path", lambda: None
    )
    return root


def _fragment(project: Path, registry: IdRegistry | None) -> Path:
    """One loom run from ``scripts/``, declaring both relative to it."""
    out = project / "frag.json"
    with loom.run(out, id_registry=registry):
        loom.set_model("demo-model", path="../models/m.bin")
        loom.add_dataset("../data/t.txt")
    return out


def _generated(project: Path) -> IdRegistry:
    registry = IdRegistry.new("r", project_root=project)
    registry.generate([project / "data", project / "models"], project)
    return registry


def _dataset_id(text: str) -> str:
    graph = json.loads(text)["@graph"]
    (spdx_id,) = [e["spdxId"] for e in graph if e["type"] == DATASET_PACKAGE_TYPE]
    return str(spdx_id)


@pytest.mark.parametrize(
    ("registry_in_run", "import_from", "key", "info"),
    [
        (True, "root", "data/t.txt", "keyed by its path: data/t.txt"),
        (False, "scripts", "data/t.txt", "keyed by its path: data/t.txt"),
        (False, "root", "../data/t.txt", f"keyed by its name: {IMPORT_NOT_FOUND}"),
    ],
    ids=["registry", "from-scripts", "unresolved"],
)
# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def test_import_keys_a_fragment_dataset_declared_from_its_script(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    registry_in_run: bool,
    import_from: str,
    key: str,
    info: str,
) -> None:
    """``../data/t.txt`` declared in ``scripts/``: keyed by the path key of
    its same-hash file (a run with a registry names it so), else by the
    name resolved from the root or the current directory, else by its
    name, the INFO telling how to fix it; the next run reuses the id."""
    run_registry = _generated(project) if registry_in_run else None
    imported = _dataset_id(_fragment(project, run_registry).read_text("utf-8"))
    registry = _generated(project)
    if import_from == "root":
        monkeypatch.chdir(project)
    caplog.set_level(logging.INFO, logger="pitloom")

    registry.import_sbom(project / "frag.json")

    entry = registry.get(DATASET_PACKAGE_TYPE, key)
    assert entry is not None and entry.spdx_id == imported
    said = [m for m in _infos(caplog) if m.startswith("ID registry: dataset ")]
    assert said == [f"ID registry: dataset ../data/t.txt {info}"]
    monkeypatch.chdir(project / "scripts")
    rerun = _dataset_id(_fragment(project, registry).read_text("utf-8"))
    assert (rerun == imported) is (key == "data/t.txt")


@pytest.mark.parametrize("registry_in_run", [True, False], ids=["registry", "none"])
def test_import_keys_a_fragment_model_by_the_held_file_entry(
    project: Path, caplog: pytest.LogCaptureFixture, registry_in_run: bool
) -> None:
    """The fragment names no file for its model: the held file entry with
    its SHA-256 gives the key, with one INFO, never the name."""
    registry = _generated(project)
    _fragment(project, registry if registry_in_run else None)
    caplog.set_level(logging.INFO, logger="pitloom")

    registry.import_sbom(project / "frag.json")

    models = [k[1] for k in registry.elements if k[0] == AI_PACKAGE_TYPE]
    assert models == ["models/m.bin"]
    entry = registry.get(AI_PACKAGE_TYPE, "models/m.bin")
    assert entry is not None
    assert entry.sha256 == hashlib.sha256(b"weights").hexdigest()
    said = [m for m in _infos(caplog) if m.startswith("ID registry: model ")]
    assert said == [
        "ID registry: model demo-model keyed by the registry's file with its "
        "SHA-256: models/m.bin"
    ]


def test_import_says_a_model_held_under_another_key_is_not_imported(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """R-keep skips the model (its id is held under its path key): the INFO
    says so, never that it was imported under its name."""
    model = _element(spdx3.ai_AIPackage, "m", f"{_NS}#AIPackage-1", _SHA_A)
    held = {(AI_PACKAGE_TYPE, "src/m.bin"): (str(model.spdxId), _SHA_B)}
    registry = make_registry(held, project_root=tmp_path)
    caplog.set_level(logging.INFO, logger="pitloom")

    registry.import_sbom(_write(tmp_path / "s.json", model))

    assert entries_of(registry) == held
    assert _infos(caplog) == [
        "ID registry: ai_AIPackage 'm' not imported: its id is held under 'src/m.bin'"
    ]
