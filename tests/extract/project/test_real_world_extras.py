# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Extras of real published ``pyproject.toml`` files, one or more per backend.

See also: ``tests/fixtures/real-world-extras/README.md`` (the fixtures) and
:mod:`tests.extract.project.test_optional_dependencies` (synthetic cases).
"""

import re
from pathlib import Path
from typing import Any

import pytest
from hatchling.metadata.core import ProjectMetadata as HatchlingMetadata
from hatchling.plugin.manager import PluginManager
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from pitloom._toml_io import load_toml_file
from pitloom.extract.project import read_project

FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "real-world-extras"
_EXTRA_TAG = re.compile(r'extra == "([^"]+)"')

_OPTIONAL = "project.optional-dependencies"
#: (backend dir, project dir, name, provenance field of the extras)
_CASES = [
    ("flit", "mousebender-2025.1", "mousebender", _OPTIONAL),
    ("flit", "etils-1.14.0", "etils", _OPTIONAL),
    ("flit", "flit-4.1.0", "flit", _OPTIONAL),
    ("hatchling", "service-identity-26.1.0", "service-identity", _OPTIONAL),
    ("hatchling", "dparse-0.6.4", "dparse", _OPTIONAL),
    (
        "setuptools",
        "dinglehopper-0.11.0",
        "dinglehopper",
        "tool.setuptools.dynamic.optional-dependencies",
    ),
    ("setuptools", "dulwich-1.2.17", "dulwich", _OPTIONAL),
    ("setuptools", "resolvelib-1.2.1", "resolvelib", _OPTIONAL),
    ("poetry", "cachy-0.3.0", "cachy", "tool.poetry.extras"),
]

#: Exact requirement strings, sorted; each as the backend's wheel writes it
#: (flit_core, Hatchling, poetry-core), spelled as Pitloom normalises it.
_PINNED = {
    "mousebender": [
        'coverage[toml]>=5.0.4; extra == "test"',
        'furo; extra == "doc"',
        'importlib-resources>=1.4.0; extra == "test"',
        "packaging>=20.9",
        'pytest-cov>=2.8.1; extra == "test"',
        'pytest>=6.0.1; extra == "test"',
        'sphinx-copybutton; extra == "doc"',
        'sphinx-prompt; extra == "doc"',
        'sphinx; extra == "doc"',
        'tomli; python_version < "3.11" and extra == "doc"',
        "typing-extensions>=4.6.0",
    ],
    # `all` lists `dparse[poetry]` etc.: Hatchling expands self-references.
    "dparse": [
        "packaging",
        'pipenv; extra == "all"',
        'pipenv; extra == "pipenv"',
        'poetry; extra == "all"',
        'poetry; extra == "poetry"',
        'pyyaml; extra == "all"',
        'pyyaml; extra == "conda"',
        'tomli; python_version < "3.11"',
    ],
    "cachy": [
        'msgpack-python<0.6.0,>=0.5; extra == "msgpack"',
        'python-memcached<2.0.0,>=1.59; extra == "memcached"',
        'redis<4.0.0,>=3.3.6; extra == "redis"',
    ],
}


def _raw_extras(data: dict[str, Any]) -> dict[str, Any]:
    """The extras table as written: ``[project]``, setuptools' dynamic
    table or Poetry's."""
    tool = data.get("tool", {})
    for table in (
        data.get("project", {}).get("optional-dependencies"),
        tool.get("setuptools", {}).get("dynamic", {}).get("optional-dependencies"),
        tool.get("poetry", {}).get("extras"),
    ):
        if table:
            return dict(table)
    return {}


@pytest.mark.parametrize(
    ("backend", "project", "name", "field"),
    _CASES,
    ids=[case[2] for case in _CASES],
)
def test_real_world_extras(backend: str, project: str, name: str, field: str) -> None:
    directory = FIXTURES / backend / project
    metadata, _config, _path = read_project(directory)

    assert metadata.name == name
    assert field in metadata.provenance["dependencies"]
    tags = {t for d in metadata.dependencies for t in _EXTRA_TAG.findall(d)}
    # An extra declared empty (etils' `epath-no-tf = []`) tags nothing.
    raw = _raw_extras(load_toml_file(directory / "pyproject.toml"))
    assert tags == {canonicalize_name(extra) for extra, reqs in raw.items() if reqs}
    if name in _PINNED:
        assert sorted(metadata.dependencies) == _PINNED[name]


def test_etils_expanded_self_reference() -> None:
    """Limit: flit_core writes etils' 66 entries as declared, keeping
    ``etils[x]; extra == "all"``; Pitloom expands each self-reference into
    the requirements it names, as Hatchling does, to 123."""
    directory = FIXTURES / "flit" / "etils-1.14.0"
    metadata, _config, _path = read_project(directory)
    raw = _raw_extras(load_toml_file(directory / "pyproject.toml"))
    assert sum(len(reqs) for reqs in raw.values()) == 66
    assert len(metadata.dependencies) == 123
    assert not [dep for dep in metadata.dependencies if dep.startswith("etils")]


def test_dparse_matches_hatchling() -> None:
    """Drift guard: Pitloom's directory read of dparse lists what
    Hatchling's own metadata core does, offline."""
    directory = FIXTURES / "hatchling" / "dparse-0.6.4"
    core = HatchlingMetadata(str(directory), PluginManager()).core
    hatchling = [str(Requirement(dep)) for dep in core.dependencies] + [
        f'{Requirement(req)}; extra == "{extra}"'
        for extra, reqs in core.optional_dependencies.items()
        for req in reqs
    ]
    metadata, _config, _path = read_project(directory)
    assert sorted(metadata.dependencies) == sorted(hatchling) == _PINNED["dparse"]
