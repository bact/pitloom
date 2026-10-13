# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Lock pins for the project's own extras (:mod:`pitloom.extract.lock._extra_pins`)
from ``uv.lock``, ``poetry.lock`` and ``pdm.lock``, through the cascade.

One lock per format resolves the same project: required ``req`` and
``both``; extra ``x`` lists ``opt`` (whose ``sub`` is not direct), ``both``
again, ``amb`` (two versions), ``gone`` (not locked), ``devpin`` (locked for
a development group only), ``vcs`` (``uv.lock``: a git source) and the
project itself; the lock's extra ``y`` lists ``undeclared``, which the
project no longer declares, and ``opt`` again.

See also: test_uv_integration.py (the real ``flask`` and ``fastapi-cli``
locks) and tests/assemble/test_deps_extras_edges.py (the edge kinds).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from pitloom.assemble import generate_project_sbom
from pitloom.core.project import ProjectMetadata
from pitloom.extract.lock import apply_locked_dependencies
from pitloom.extract.lock._extra_pins import apply_extra_pins
from pitloom.extract.project import read_project

_HASH = "a" * 64
_REG = 'source = { registry = "https://pypi.org/simple" }'

_PYPROJECT = """\
[project]
name = "demo"
version = "1.0"
dependencies = ["req>=1", "both>=1"]

[project.optional-dependencies]
x = ["opt>=1", "both>=1", "gone", "amb", "devpin", "demo[y]"]
y = []
"""

_DECLARED = [
    "not a requirement!",  # first: the names after it are still read
    "req>=1",
    "both>=1",
    'opt>=1; extra == "x"',
    'both>=1; extra == "x"',
    'gone; extra == "x"',
    'amb; extra == "x"',
    'devpin; extra == "x"',
    'vcs; extra == "x"',
    "demo[y]; extra == 'x'",
]


def _uv_pkg(name: str, version: str, extra: str = "") -> str:
    return f'[[package]]\nname = "{name}"\nversion = "{version}"\n{_REG}\n{extra}\n'


_UV_LOCK = (
    'version = 1\nrevision = 3\nrequires-python = ">=3.10"\n\n'
    '[[package]]\nname = "demo"\nversion = "1.0"\nsource = { editable = "." }\n'
    'dependencies = [{ name = "req" }, { name = "both" }]\n\n'
    "[package.optional-dependencies]\n"
    'x = [{ name = "opt" }, { name = "both" }, { name = "demo", extra = ["y"] },'
    f' {{ name = "amb", version = "1.0", {_REG}, marker = "os_name == \'nt\'" }},'
    f' {{ name = "amb", version = "2.0", {_REG}, marker = "os_name != \'nt\'" }},'
    ' { name = "vcs" }, 1]\n'
    'y = [{ name = "undeclared" }, { name = "opt" }]\nw = "opt"\nv = 1\n\n'
    "[package.dev-dependencies]\n"
    'dev = [{ name = "devpin" }]\n\n'
    + _uv_pkg("req", "1.0")
    + _uv_pkg("both", "1.5")
    + _uv_pkg(
        "opt",
        "2.0",
        'dependencies = [{ name = "sub" }]\n'
        f'sdist = {{ url = "https://x/opt-2.0.tar.gz", hash = "sha256:{_HASH}" }}',
    )
    + _uv_pkg("sub", "3.0")
    + _uv_pkg("amb", "1.0")
    + _uv_pkg("amb", "2.0")
    + _uv_pkg("devpin", "1.0")
    + _uv_pkg("undeclared", "1.0")
    + '[[package]]\nname = "vcs"\nversion = "1.0"\nsource = { git = "https://x/vcs" }\n'
)


def _poetry_pkg(
    name: str, version: str, groups: str = '"main"', extra: str = ""
) -> str:
    optional = "true" if groups == '"main"' else "false"
    return (
        f'[[package]]\nname = "{name}"\nversion = "{version}"\n'
        f"optional = {optional}\ngroups = [{groups}]\n{extra}\n"
    )


_POETRY_LOCK = (
    _poetry_pkg("req", "1.0", '"main", "x"')
    + _poetry_pkg("both", "1.5", '"main", "x"')
    + _poetry_pkg(
        "opt",
        "2.0",
        extra=f'files = [{{ file = "opt-2.0.tar.gz", hash = "sha256:{_HASH}" }}]\n'
        '[package.dependencies]\nsub = "*"',
    )
    + _poetry_pkg("sub", "3.0")
    + _poetry_pkg("amb", "1.0")
    + _poetry_pkg("amb", "2.0")
    + _poetry_pkg("devpin", "1.0", '"dev"')
    + _poetry_pkg("undeclared", "1.0")
    + '[[package]]\nname = "gone"\n\n'
    + '[extras]\nx = ["opt", "both", "amb", "gone", "devpin", "not valid!", 3]\n'
    'y = ["undeclared"]\nz = "opt"\n\n'
    '[metadata]\nlock-version = "2.1"\npython-versions = ">=3.10"\n'
    'content-hash = "0"\n'
)


def _pdm_pkg(name: str, version: str, groups: str, extra: str = "") -> str:
    return (
        f'[[package]]\nname = "{name}"\nversion = "{version}"\n'
        f"groups = [{groups}]\n{extra}\n"
    )


_PDM_LOCK = (
    '[metadata]\ngroups = ["default", "x", "y", "dev"]\n'
    'strategy = ["inherit_metadata"]\nlock_version = "4.5.0"\n'
    'content_hash = "sha256:0"\n\n'
    + _pdm_pkg("req", "1.0", '"default"')
    + _pdm_pkg("both", "1.5", '"default", "x"')
    + _pdm_pkg(
        "opt",
        "2.0",
        '"dev", "x"',
        'dependencies = ["sub"]\n'
        f'files = [{{ file = "opt-2.0.tar.gz", hash = "sha256:{_HASH}" }}]',
    )
    + _pdm_pkg("sub", "3.0", '"x"')
    + _pdm_pkg("amb", "1.0", '"x"')
    + _pdm_pkg("amb", "2.0", '"x"')
    + _pdm_pkg("devpin", "1.0", '"dev"')
    + _pdm_pkg("undeclared", "1.0", '"y"')
    + _pdm_pkg("vcs", "1.0", '"x"', 'git = "https://x/vcs"')
    + '[[package]]\nname = "gone"\ngroups = ["x"]\n'
)

_LOCKS = {"uv.lock": _UV_LOCK, "poetry.lock": _POETRY_LOCK, "pdm.lock": _PDM_LOCK}
_CLOSURE = ["req==1.0", "both==1.5"]


def _project(tmp_path: Path, lock_name: str) -> Path:
    (tmp_path / "pyproject.toml").write_text(_PYPROJECT, encoding="utf-8")
    (tmp_path / lock_name).write_text(_LOCKS[lock_name], encoding="utf-8")
    return tmp_path


def _metadata(prior: str | None = None) -> ProjectMetadata:
    metadata = ProjectMetadata(name="demo", dependencies=list(_DECLARED))
    if prior is not None:  # applied before the cascade (`_try_read_poetry()`)
        metadata.locked_dependencies = list(_CLOSURE)
        metadata.provenance["locked_dependencies"] = (
            f"Source: {prior} | Method: resolved_lockfile"
        )
    return metadata


@pytest.mark.parametrize(
    ("lock_name", "prior"),
    [
        ("uv.lock", None),
        ("poetry.lock", None),
        ("poetry.lock", "poetry.lock"),
        ("pdm.lock", None),
    ],
    ids=["uv", "poetry", "poetry-prior", "pdm"],
)
def test_extra_pinned_once_direct_only(
    tmp_path: Path, lock_name: str, prior: str | None, caplog: pytest.LogCaptureFixture
) -> None:
    """``opt`` pinned with its hash; ``both`` (required) once; ``gone``
    (not locked), ``amb`` (ambiguous, warned), ``devpin`` (development
    group), ``undeclared`` (stale extra) and ``sub`` (not direct) unpinned.
    """
    metadata = _metadata(prior)

    with caplog.at_level(logging.WARNING):
        apply_locked_dependencies(metadata, _project(tmp_path, lock_name))

    assert metadata.locked_dependencies == [*_CLOSURE, "opt==2.0"]
    assert metadata.locked_dependency_hashes == {"opt": _HASH}
    messages = [record.getMessage() for record in caplog.records]
    assert len([m for m in messages if "'amb'" in m]) == 1  # warned, once
    assert len([m for m in messages if "'gone'" in m]) <= 1  # not warned again
    assert not [m for m in messages if "'demo'" in m]  # never asked for


@pytest.mark.parametrize("lock_name", sorted(_LOCKS), ids=["pdm", "poetry", "uv"])
def test_extra_pins_deterministic_and_idempotent(
    tmp_path: Path, lock_name: str
) -> None:
    project_dir = _project(tmp_path, lock_name)
    first, second = _metadata(), _metadata()

    apply_locked_dependencies(first, project_dir)
    apply_locked_dependencies(second, project_dir)
    snapshot = list(first.locked_dependencies)
    apply_locked_dependencies(first, project_dir)

    assert "opt==2.0" in snapshot
    assert first.locked_dependencies == second.locked_dependencies == snapshot


def test_extra_pins_sorted_by_name(tmp_path: Path) -> None:
    """By PEP 503 name (``opt`` before ``opt-b``, unlike the pin strings),
    any spelling matched."""
    lock = _UV_LOCK.replace(
        'x = [{ name = "opt" }',
        'x = [{ name = "Zed" }, { name = "opt-b" }, { name = "opt" }',
    )
    lock += _uv_pkg("zed", "1.0") + _uv_pkg("opt-b", "1.0")
    (tmp_path / "uv.lock").write_text(lock, encoding="utf-8")
    metadata = ProjectMetadata(
        name="demo",
        dependencies=['ZED; extra == "x"', 'Opt_B; extra == "x"', 'opt; extra == "x"'],
    )

    apply_locked_dependencies(metadata, tmp_path)

    assert metadata.locked_dependencies[-3:] == ["opt==2.0", "opt-b==1.0", "zed==1.0"]


def test_extra_pin_hashes_join_closure_hashes(tmp_path: Path) -> None:
    hashed = 'sdist = { url = "https://x/req-1.0.tar.gz", hash = "sha256:' + "b" * 64
    lock = _UV_LOCK.replace(
        _uv_pkg("req", "1.0"), _uv_pkg("req", "1.0", hashed + '" }')
    )
    (tmp_path / "uv.lock").write_text(lock, encoding="utf-8")
    metadata = _metadata()

    apply_locked_dependencies(metadata, tmp_path)

    assert metadata.locked_dependency_hashes == {"req": "b" * 64, "opt": _HASH}


@pytest.mark.parametrize(
    "lock_name", ["pdm.lock", "poetry.lock"], ids=["pdm", "poetry"]
)
def test_extra_pins_match_any_spelling(tmp_path: Path, lock_name: str) -> None:
    """Extra, group, ``[extras]`` and package names compared per PEP 503."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\n[project.optional-dependencies]\n'
        'X_Extra = ["zed-pkg"]\n',
        encoding="utf-8",
    )
    lock = (
        '[metadata]\nlock_version = "4.5.0"\n\n'
        + _pdm_pkg("Zed_Pkg", "1.0", '"X_Extra"')
        if lock_name == "pdm.lock"
        else '[metadata]\nlock-version = "2.1"\n\n'
        + _poetry_pkg("Zed_Pkg", "1.0")
        + '[extras]\nX_Extra = ["ZED.pkg"]\n'
    )
    (tmp_path / lock_name).write_text(lock, encoding="utf-8")
    metadata = ProjectMetadata(
        name="demo", dependencies=['zed-pkg; extra == "x-extra"']
    )

    apply_locked_dependencies(metadata, tmp_path)

    assert metadata.locked_dependencies == ["Zed_Pkg==1.0"]


@pytest.mark.parametrize(
    "lock_name", ["pdm.lock", "poetry.lock"], ids=["pdm", "poetry"]
)
def test_lock_without_package_table_pins_nothing(
    tmp_path: Path, lock_name: str
) -> None:
    lock = (
        '[metadata]\ngroups = ["default"]\nlock_version = "4.5.0"\n'
        if lock_name == "pdm.lock"
        else '[metadata]\nlock-version = "2.1"\n[extras]\nx = ["opt"]\n'
    )
    (tmp_path / "pyproject.toml").write_text(_PYPROJECT, encoding="utf-8")
    (tmp_path / lock_name).write_text(lock, encoding="utf-8")
    metadata = _metadata()

    apply_locked_dependencies(metadata, tmp_path)

    assert not metadata.locked_dependencies


def test_poetry_pins_only_names_its_extras_table_lists(tmp_path: Path) -> None:
    """``sub`` is locked (``main``, optional) for ``opt``, but no extra of
    the lock lists it: not pinned."""
    metadata = ProjectMetadata(
        name="demo", dependencies=['opt; extra == "x"', 'sub; extra == "x"']
    )

    apply_locked_dependencies(metadata, _project(tmp_path, "poetry.lock"))

    assert metadata.locked_dependencies == [*_CLOSURE, "opt==2.0"]


def test_uv_workspace_root_found_by_project_name(tmp_path: Path) -> None:
    """Two local members and no ``pyproject.toml`` to read the name from:
    the project's own name picks its entry."""
    editable = 'source = { editable = "." }'
    lock = (
        "version = 1\nrevision = 3\n\n"
        f'[[package]]\nname = "other"\nversion = "1.0"\n{editable}\n\n'
        f'[[package]]\nname = "demo"\nversion = "1.0"\n{editable}\n\n'
        '[package.optional-dependencies]\nx = [{ name = "opt" }]\n\n'
        + _uv_pkg("opt", "2.0")
    )
    (tmp_path / "uv.lock").write_text(lock, encoding="utf-8")
    metadata = ProjectMetadata(name="demo", dependencies=['opt; extra == "x"'])

    apply_locked_dependencies(metadata, tmp_path)

    assert metadata.locked_dependencies == ["opt==2.0"]


@pytest.mark.parametrize(
    "root_extra",
    ["", "optional-dependencies = 1\n"],
    ids=["absent", "not-a-table"],
)
def test_uv_root_without_usable_extras(tmp_path: Path, root_extra: str) -> None:
    lock = (
        'version = 1\nrevision = 3\n\n[[package]]\nname = "demo"\nversion = "1.0"\n'
        f'source = {{ editable = "." }}\n{root_extra}\n' + _uv_pkg("opt", "2.0")
    )
    (tmp_path / "uv.lock").write_text(lock, encoding="utf-8")
    metadata = ProjectMetadata(name="demo", dependencies=['opt; extra == "x"'])

    apply_locked_dependencies(metadata, tmp_path)

    assert not metadata.locked_dependencies


@pytest.mark.parametrize(
    ("declared", "wanted"),
    [
        ('foo; extra == "x"', {"foo"}),
        ('foo; extra == "x" and python_version < "3.9"', {"foo"}),
        ('foo; extra == "x" or python_version < "3.9"', set()),
        ('foo; extra != "x"', set()),
        ("foo; python_version < '3.9'", set()),
    ],
    ids=["gated", "gated-and", "or-non-extra", "not-equal", "no-extra"],
)
def test_extra_pins_ask_only_what_the_edges_call_optional(
    tmp_path: Path, declared: str, wanted: set[str]
) -> None:
    """Regression: a marker naming ``extra`` anywhere counted as gated, so a
    dependency recorded as required (its gate does not isolate) was still
    asked for an extra's pin. One rule decides both
    (:func:`pitloom.core.extra_gate.is_extra_gated`)."""
    asked: list[frozenset[str]] = []

    def extractor(_dir: Path, _name: str, names: frozenset[str]) -> list[str]:
        asked.append(names)
        return []

    metadata = ProjectMetadata(name="demo", dependencies=[declared])
    apply_extra_pins(metadata, tmp_path, extractor, lambda _dir, _pins: None)

    assert asked == [frozenset(wanted)]


def test_pdm_without_pyproject_extras_pins_nothing(tmp_path: Path) -> None:
    (tmp_path / "pdm.lock").write_text(_PDM_LOCK, encoding="utf-8")
    metadata = _metadata()

    apply_locked_dependencies(metadata, tmp_path)

    assert metadata.locked_dependencies == _CLOSURE


def test_stage_flag_gates_extra_pins(tmp_path: Path) -> None:
    project_dir = _project(tmp_path, "uv.lock")

    source, _config, _path = read_project(project_dir)
    build, _config, _path = read_project(project_dir, include_locked_dependencies=False)

    assert "opt==2.0" in source.locked_dependencies
    assert not build.locked_dependencies
    assert not build.locked_dependency_hashes


def test_sbom_pins_extra_package_with_optional_edge(tmp_path: Path) -> None:
    """End to end: the extra's package carries the locked version, purl and
    hash; its edge stays ``hasOptionalDependency``."""
    (tmp_path / "demo").mkdir()
    (tmp_path / "demo" / "__init__.py").write_text("", encoding="utf-8")
    sbom = generate_project_sbom(_project(tmp_path, "uv.lock"), offline=True)

    graph = json.loads(sbom)["@graph"]
    (opt,) = [n for n in graph if n.get("name") == "opt"]
    (edge,) = [n for n in graph if n.get("to") == [opt["spdxId"]]]
    assert opt["software_packageVersion"] == "2.0"
    assert opt["software_packageUrl"] == "pkg:pypi/opt@2.0"
    assert [h["hashValue"] for h in opt["verifiedUsing"]] == [_HASH]
    assert (edge["type"], edge["relationshipType"], edge["comment"]) == (
        "Relationship",
        "hasOptionalDependency",
        "extras: x",
    )
    assert "scope" not in edge
    assert not [n for n in graph if n.get("name") == "sub"]


_GIT_LOCKS = {
    "uv.lock": (
        'version = 1\nrevision = 3\n\n[[package]]\nname = "demo"\nversion = "1.0"\n'
        'source = { editable = "." }\ndependencies = [{ name = "vcs" }]\n\n'
        '[package.optional-dependencies]\nx = [{ name = "vcs" }]\n\n'
        '[[package]]\nname = "vcs"\nversion = "1.0"\nsource = { git = "https://x/v" }\n'
    ),
    "poetry.lock": (
        '[[package]]\nname = "vcs"\nversion = "1.0"\noptional = false\n'
        'groups = ["main"]\n[package.source]\ntype = "git"\nurl = "https://x/v"\n\n'
        '[extras]\nx = ["vcs"]\n\n[metadata]\nlock-version = "2.1"\n'
        'python-versions = ">=3.10"\ncontent-hash = "0"\n'
    ),
    "pdm.lock": (
        '[metadata]\ngroups = ["default", "x"]\nlock_version = "4.5.0"\n'
        'content_hash = "sha256:0"\n\n'
        + _pdm_pkg("vcs", "1.0", '"default", "x"', 'git = "https://x/v"')
    ),
}


@pytest.mark.parametrize("lock_name", sorted(_GIT_LOCKS), ids=["pdm", "poetry", "uv"])
def test_required_and_extra_git_dependency_warned_once(
    tmp_path: Path, lock_name: str, caplog: pytest.LogCaptureFixture
) -> None:
    """Regression: a name both required and in an extra was asked for again
    after the runtime closure's pass, so its lock warning (here: git-sourced)
    printed twice. Only names an extra alone gates are asked for."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\ndependencies = ["vcs"]\n'
        '[project.optional-dependencies]\nx = ["vcs"]\n',
        encoding="utf-8",
    )
    (tmp_path / lock_name).write_text(_GIT_LOCKS[lock_name], encoding="utf-8")
    metadata = ProjectMetadata(name="demo", dependencies=["vcs", 'vcs; extra == "x"'])

    with caplog.at_level(logging.WARNING):
        apply_locked_dependencies(metadata, tmp_path)

    assert not metadata.locked_dependencies
    assert len([m for m in caplog.messages if "'vcs'" in m]) == 1, caplog.messages


@pytest.mark.parametrize(
    ("dependencies", "asked"),
    [
        (['opt; extra == "x"'], True),
        (['opt; python_version < "3.11" and "x" == extra'], True),
        (["opt"], False),
        (['opt; os_name == "extra"'], False),
        (['opt; extra == "x"', "opt"], False),
    ],
    ids=["gated", "reversed", "required", "quoted-extra", "required-too"],
)
def test_only_extra_gated_names_are_asked_for(
    tmp_path: Path, dependencies: list[str], asked: bool
) -> None:
    """A required name is the runtime closure's: never asked for again."""
    (tmp_path / "uv.lock").write_text(
        _UV_LOCK.replace('dependencies = [{ name = "req" }, { name = "both" }]', ""),
        encoding="utf-8",
    )
    metadata = ProjectMetadata(name="demo", dependencies=dependencies)

    apply_locked_dependencies(metadata, tmp_path)

    assert ("opt==2.0" in metadata.locked_dependencies) is asked
