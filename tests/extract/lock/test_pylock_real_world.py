# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Real-world PEP 751 ``pylock.toml`` fixtures
(``tests/fixtures/real-world-locks/pylock/``) read through
:func:`pitloom.extract.lock.pylock.extract_pylock_dependencies`, the
cascade's entry, with every expectation computed from the file itself;
plus the claims ``tests/fixtures/real-world-locks/README.md`` makes about
them (section "pylock.toml producers and extras").

See also: test_pylock.py (synthetic reader tests), test_pylock_markers.py
(group/extras marker evaluation), test_uv_integration.py (the same
projects read from their ``uv.lock``).
"""

from __future__ import annotations

import hashlib
import logging
import re
import shutil
from pathlib import Path
from typing import Any

import pytest
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

from pitloom._toml_io import load_toml_file
from pitloom.core.project import ProjectMetadata
from pitloom.extract.lock.cascade import apply_locked_dependencies
from pitloom.extract.lock.pylock import extract_pylock_dependencies

_LOCKS_ROOT = Path(__file__).parent.parent.parent / "fixtures" / "real-world-locks"
_PYLOCK = _LOCKS_ROOT / "pylock"
_README = _LOCKS_ROOT / "README.md"
_NON_REGISTRY = ("vcs", "directory", "archive")


def _short_id(lock: Path) -> str:
    """``flask/no-default-groups`` for ``flask-3.1.3-uv-export/pylock.no-...``."""
    project = re.sub(r"-\d.*$", "", lock.parent.name)
    variant = lock.stem.removeprefix("pylock").lstrip(".") or "pylock"
    return f"{project}/{variant}"


_LOCKS = {_short_id(p): p for p in sorted(_PYLOCK.glob("*/pylock*.toml"))}


def _toml(path: Path) -> dict[str, Any]:
    return dict(load_toml_file(path))


def _names(short_id: str) -> set[str]:
    """Canonical names of every ``[[packages]]`` entry of one fixture."""
    return {canonicalize_name(p["name"]) for p in _toml(_LOCKS[short_id])["packages"]}


def _declared(project_dir: Path, table: str, keys: list[str]) -> set[str]:
    """Canonical names one or more dependency-groups (*table*
    ``dependency-groups``) or extras (``optional-dependencies``) list,
    following ``include-group`` and self-referencing extras."""
    data = _toml(project_dir / "pyproject.toml")
    entries = data[table] if table in data else data["project"][table]
    own = canonicalize_name(data.get("project", {}).get("name", ""))
    names: set[str] = set()
    todo = list(keys)
    while todo:
        for item in entries[todo.pop()]:
            if isinstance(item, dict):
                todo.append(item["include-group"])
                continue
            req = Requirement(item)
            if canonicalize_name(req.name) == own:
                todo.extend(req.extras)
            else:
                names.add(canonicalize_name(req.name))
    return names


def _expected(
    data: dict[str, Any],
) -> tuple[set[tuple[str, Version]], dict[str, str]]:
    """Pins, and warned names with their reason, that the reader's docstring
    contract gives for one file: a non-default ``'g' in dependency_groups``
    entry is dropped silently; a ``vcs``/``directory``/``archive`` entry is
    dropped with a ``WARNING:``; a name at two PEP 440-distinct versions is
    dropped with a ``WARNING:``; any other marker is not evaluated, so its
    entry stays."""
    defaults = {canonicalize_name(g) for g in data.get("default-groups", [])}
    versions: dict[str, set[Version]] = {}
    warned: dict[str, str] = {}
    for pkg in data["packages"]:
        groups = re.findall(r"'([^']+)' in dependency_groups", pkg.get("marker", ""))
        if {canonicalize_name(g) for g in groups} - defaults:
            continue
        source = next((key for key in _NON_REGISTRY if key in pkg), None)
        if source:
            warned[pkg["name"]] = f"{source}-sourced"
            continue
        name = canonicalize_name(pkg["name"])
        versions.setdefault(name, set()).add(Version(pkg["version"]))
    warned |= {n: "conflicting versions" for n, f in versions.items() if len(f) > 1}
    pins = {
        (name, v) for name, found in versions.items() if len(found) == 1 for v in found
    }
    return pins, warned


def _as_lock_dir(tmp_path: Path, lock: Path) -> Path:
    """Copy one variant beside its project files as ``pylock.toml``, the only
    name the cascade reads."""
    for item in lock.parent.iterdir():
        if not item.name.startswith("pylock"):
            shutil.copyfile(item, tmp_path / item.name)
    shutil.copyfile(lock, tmp_path / "pylock.toml")
    return tmp_path


@pytest.mark.parametrize("short_id", list(_LOCKS), ids=list(_LOCKS))
def test_reader_matches_independent_parse(
    short_id: str, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    lock = _LOCKS[short_id]
    data = _toml(lock)
    pins, warned = _expected(data)

    with caplog.at_level(logging.WARNING):
        result = extract_pylock_dependencies(_as_lock_dir(tmp_path, lock))

    assert result is not None
    got = [dep.split("==") for dep in result]
    assert {(canonicalize_name(n), Version(v)) for n, v in got} == pins
    assert len(result) == len(pins)
    messages = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(messages) == len(warned)
    for name, reason in warned.items():
        assert any(f"'{name}'" in m and reason in m for m in messages), name
    # A directory entry is always the project itself, at the project root.
    project = _toml(lock.parent / "pyproject.toml").get("project", {})
    for pkg in data["packages"]:
        if "directory" in pkg:
            assert canonicalize_name(pkg["name"]) == canonicalize_name(project["name"])
            assert pkg["directory"]["path"] == "."


def test_environment_markers_are_kept_not_evaluated() -> None:
    """Guards against a vacuous pass of the parse test above: the fixtures
    hold entries gated on markers other than groups/extras, and they pin."""
    marked = {
        (short_id, canonicalize_name(p["name"]))
        for short_id, lock in _LOCKS.items()
        for p in _toml(lock)["packages"]
        if "marker" in p and "dependency_groups" not in p["marker"]
    }
    assert ("flask/extra-async-no-default-groups", "typing-extensions") in marked
    assert len({short_id for short_id, _ in marked}) >= 10


_FLASK = _PYLOCK / "flask-3.1.3-uv-export"
_ABI3 = _PYLOCK / "abi3audit-0.0.26-uv-export"
_ATTEST = _PYLOCK / "pylock-attestations-0.0.1a2-uv-export"


@pytest.mark.parametrize(
    ("base", "wider", "must_add", "added_count"),
    [
        (
            "flask/no-default-groups",
            "flask/extra-async-no-default-groups",
            {"asgiref", "typing-extensions"},
            2,
        ),
        (
            "flask/extra-async-no-default-groups",
            "flask/all-extras-no-default-groups",
            {"python-dotenv"},
            1,
        ),
        (
            "flask/no-default-groups",
            "flask/default",
            _declared(
                _FLASK, "dependency-groups", ["dev", "pre-commit", "tests", "typing"]
            )
            - _names("flask/no-default-groups"),
            None,
        ),
        (
            "fastapi-cli/no-dev",
            "fastapi-cli/extra-standard-no-dev",
            {"fastapi-cloud-cli"},
            15,
        ),
        (
            "abi3audit/no-dev",
            "abi3audit/default",
            _declared(_ABI3, "dependency-groups", ["dev"]),
            None,
        ),
        (
            "pylock-attestations/default",
            "pylock-attestations/extra-dev",
            _declared(_ATTEST, "optional-dependencies", ["dev"]),
            None,
        ),
    ],
    ids=[
        "flask-async",
        "flask-all-extras",
        "flask-groups",
        "fastapi-standard",
        "abi3audit-dev",
        "attestations-dev",
    ],
)
def test_readme_variant_differences(
    base: str, wider: str, must_add: set[str], added_count: int | None
) -> None:
    """README: each flag only adds packages to the base selection."""
    base_names, wider_names = _names(base), _names(wider)
    added = wider_names - base_names
    assert base_names <= wider_names
    assert must_add and must_add <= added
    assert added_count is None or len(added) == added_count


def _entries(short_id: str, name: str) -> list[dict[str, Any]]:
    packages = _toml(_LOCKS[short_id])["packages"]
    return [p for p in packages if canonicalize_name(p["name"]) == name]


def test_readme_shape_claims() -> None:
    """The README's per-file statements, other than the variant differences."""
    group_keys = {"extras", "dependency-groups", "default-groups"}
    for short_id, lock in _LOCKS.items():
        data = _toml(lock)
        is_pipenv = short_id.startswith("pipenv/")
        assert bool(group_keys & data.keys()) is is_pipenv, short_id
        markers = " ".join(p.get("marker", "") for p in data["packages"])
        assert "in extras" not in markers
        assert ("in dependency_groups" in markers) is is_pipenv, short_id
    pipenv = _toml(_LOCKS["pipenv/pylock"])
    assert (pipenv["extras"], pipenv["dependency-groups"]) == ([], ["dev"])
    assert pipenv["default-groups"] == ["default"]
    # flask: entry counts, and click split by python_full_version.
    assert len(_toml(_LOCKS["flask/default"])["packages"]) == 62
    assert len(_toml(_LOCKS["flask/no-default-groups"])["packages"]) == 11
    for short_id in (s for s in _LOCKS if s.startswith("flask/")):
        clicks = _entries(short_id, "click")
        assert len(clicks) == 2 and all(
            "python_full_version" in c["marker"] for c in clicks
        )
    # fastapi-cli: uvicorn[standard]'s own extras are in both selections.
    standard = {"httptools", "uvloop", "watchfiles"}
    assert standard <= _names("fastapi-cli/no-dev")
    assert standard <= _names("fastapi-cli/extra-standard-no-dev")
    # pip and pdfly fold their groups in; pip has no [project] and no self entry.
    pip_dir = _LOCKS["pip/pylock"].parent
    assert "project" not in _toml(pip_dir / "pyproject.toml")
    assert _declared(pip_dir, "dependency-groups", ["build"]) <= _names("pip/pylock")
    assert not any("directory" in p for p in _toml(_LOCKS["pip/pylock"])["packages"])
    pdfly_dir = _LOCKS["pdfly/pylock"].parent
    assert _declared(pdfly_dir, "dependency-groups", ["dev", "docs"]) <= _names(
        "pdfly/pylock"
    )
    assert _entries("pdfly/pylock", "pdfly")[0]["directory"] == {"path": "."}
    assert "optional-dependencies" not in _toml(_ABI3 / "pyproject.toml")["project"]
    # uv: the project is an editable directory entry, unless it is virtual.
    assert "build-system" not in _toml(_ATTEST / "pyproject.toml")
    for short_id in (s for s in _LOCKS if _LOCKS[s].parent.name.endswith("uv-export")):
        own = re.sub(r"/.*$", "", short_id)
        selves = _entries(short_id, own)
        expected = (
            [] if own == "pylock-attestations" else [{"path": ".", "editable": True}]
        )
        assert [p["directory"] for p in selves] == expected, short_id


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _readme_rows() -> list[list[str]]:
    """Cells of the producers table rows (those whose last cell is a sha256)."""
    rows = []
    for line in _README.read_text(encoding="utf-8").splitlines():
        cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
        if len(cells) == 7 and re.match(r"[0-9a-f]{8}", cells[-1]):
            rows.append(cells)
    return rows


def _check_row(cells: list[str]) -> list[Path]:
    """Assert one table row's sizes, sha256s (an abbreviated ``abcd1234...``
    is a prefix), source ``uv.lock`` sha and export command; return its
    files."""
    directory, files, source, _licence, flags, sizes, shas = cells
    paths = []
    for name, size, sha in zip(
        files.split("`, `"), sizes.split(", "), shas.split("`, `"), strict=True
    ):
        path = _PYLOCK / directory / name
        assert path.stat().st_size == int(size), path
        assert _sha256(path).startswith(sha.removesuffix("...")), path
        paths.append(path)
    uv_lock = re.match(r"\.\./uv/([^`]+)` \(`([0-9a-f]+)\.\.\.", source)
    if uv_lock:
        assert _sha256(_LOCKS_ROOT / "uv" / uv_lock[1]).startswith(uv_lock[2])
    if flags.startswith(("--", "uv export")):
        command = flags if flags.startswith("--") else ""
        header = paths[0].read_text(encoding="utf-8").splitlines()[1]
        assert header.endswith(
            f"--format pylock.toml {command} -o {files}".replace("  ", " ")
        )
    return paths


def test_readme_table_sizes_and_hashes() -> None:
    """The producers table lists every produced pylock with its true size and
    sha256; files said to be copied from ``../uv/`` are byte-identical."""
    listed = {path for row in _readme_rows() for path in _check_row(row)}
    produced = {_LOCKS["pip/pylock"], _LOCKS["pdfly/pylock"]}
    produced |= {p for p in _LOCKS.values() if p.parent.name.endswith("uv-export")}
    assert produced <= listed
    for export in (p for p in _PYLOCK.glob("*-uv-export") if p != _ATTEST):
        upstream_dir = _LOCKS_ROOT / "uv" / export.name.removesuffix("-uv-export")
        for item in export.iterdir():
            if not item.name.startswith("pylock"):
                assert item.read_bytes() == (upstream_dir / item.name).read_bytes()


@pytest.mark.parametrize(
    ("variant", "pinned"),
    [
        ("extra-async-no-default-groups", True),
        ("default", True),
        ("no-default-groups", False),
    ],
    ids=[
        "flask-async-pins-today",
        "flask-default-pins-today",
        "flask-runtime-pins-today",
    ],
)
def test_own_extra_pinned_only_when_the_export_selected_it(
    variant: str, pinned: bool, tmp_path: Path
) -> None:
    """Current behaviour, through the cascade: the pylock reader adds no pin
    for the project's own extras (uv and pip write no ``extras`` key or
    ``'x' in extras`` marker), but a variant whose selection includes an
    extra's package (``--extra async``, or the ``tests``/``typing`` default
    groups naming ``asgiref``) pins it like any other entry, at that file's
    version. ``read_project()`` is not used: licence matching on the vendored
    ``LICENSE.txt`` alone takes ~2 s."""
    lock = _FLASK / f"pylock.{variant}.toml"
    pyproject = _toml(_FLASK / "pyproject.toml")["project"]
    assert "asgiref>=3.2" in pyproject["optional-dependencies"]["async"]
    metadata = ProjectMetadata(name=pyproject["name"])

    apply_locked_dependencies(metadata, _as_lock_dir(tmp_path, lock))

    expected = [
        f"asgiref=={e['version']}" for e in _entries(_short_id(lock), "asgiref")
    ]
    assert [d for d in metadata.locked_dependencies if d.startswith("asgiref==")] == (
        expected
    )
    assert bool(expected) is pinned
    assert metadata.provenance["locked_dependencies"].startswith(
        "Source: pylock.toml |"
    )
