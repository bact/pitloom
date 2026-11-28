# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the typed lock origin (:mod:`pitloom.core.lock_origin`) and
the document id it seeds: each lock route keeps its id, and the wording of
the provenance string is no id input.

See also: tests/core/test_models.py (the ids pinned on the seed text, and
the pylock.toml and poetry.lock routes).
"""

import json
from pathlib import Path

import pytest

from pitloom.assemble import project_document_id
from pitloom.core import project as project_module
from pitloom.core.lock_origin import LockOrigin, lock_provenance, lock_seed_text
from pitloom.core.project import ProjectMetadata, merge_project_metadata
from pitloom.extract.project import read_project

pytestmark = pytest.mark.platform

_PROJECT = '[project]\nname = "demo"\nversion = "1.0.0"\n'
_POETRY_PROJECT = '[tool.poetry]\nname = "demo"\nversion = "1.0.0"\n'
_UV_LOCK = (
    'version = 1\nrevision = 1\nrequires-python = ">=3.10"\n'
    '[[package]]\nname = "demo"\nversion = "1.0.0"\n'
    'source = { editable = "." }\n'
    'dependencies = [{ name = "requests" }]\n\n'
    '[[package]]\nname = "requests"\nversion = "2.31.0"\n'
    'source = { registry = "https://pypi.org/simple" }\n'
)
_PDM_LOCK = (
    '[[package]]\nname = "requests"\nversion = "2.31.0"\n'
    'groups = ["default"]\n[metadata]\nlock_version = "4.5.1"\n'
)
_PIPFILE_LOCK = json.dumps(
    {"_meta": {"pipfile-spec": 6}, "default": {"requests": {"version": "==2.31.0"}}}
)
_POETRY_LOCK = (
    '[[package]]\nname = "requests"\nversion = "2.31.0"\ngroups = ["main"]\n'
    '[metadata]\nlock-version = "2.1"\n'
)

#: (id, files of the project, the origin its reader records, today's id).
_ROUTES = [
    (
        "uv",
        {"pyproject.toml": _PROJECT, "uv.lock": _UV_LOCK},
        LockOrigin("uv.lock", "resolved_lockfile"),
        "https://spdx.org/spdxdocs/demo-3ed4d0cf-033c-5718-a6ac-0a53528fe7ee",
    ),
    (
        "pdm",
        {"pyproject.toml": _PROJECT, "pdm.lock": _PDM_LOCK},
        LockOrigin("pdm.lock", "resolved_lockfile"),
        "https://spdx.org/spdxdocs/demo-588c2071-b5a0-5883-8de3-52c57bb46b22",
    ),
    (
        "pipfile",
        {"pyproject.toml": _PROJECT, "Pipfile.lock": _PIPFILE_LOCK},
        LockOrigin("Pipfile.lock", "resolved_lockfile"),
        "https://spdx.org/spdxdocs/demo-50cac38e-f151-5cb3-a617-6e4cc775d2d4",
    ),
    (
        "requirements",
        {"pyproject.toml": _PROJECT, "requirements.txt": "requests==2.31.0\n"},
        LockOrigin("requirements.txt", "pinned_requirements"),
        "https://spdx.org/spdxdocs/demo-f154939d-ad63-5c6c-b3a5-1ee96752cde5",
    ),
    (
        "supersedes",
        {
            "pyproject.toml": _POETRY_PROJECT,
            "poetry.lock": _POETRY_LOCK,
            "uv.lock": _UV_LOCK,
        },
        LockOrigin("uv.lock", "resolved_lockfile", "poetry.lock"),
        "https://spdx.org/spdxdocs/demo-32d2192f-7005-5339-8565-243b894357bc",
    ),
]
_ROUTE_PARAMS = [pytest.param(*route[1:], id=route[0]) for route in _ROUTES]


def _write(root: Path, files: dict[str, str]) -> Path:
    root.mkdir()
    # write_bytes: the id covers file digests, so no CRLF on Windows.
    for name, text in files.items():
        (root / name).write_bytes(text.encode())
    return root


@pytest.mark.parametrize(
    ("origin", "text"),
    [
        (
            LockOrigin("pylock.toml", "resolved_lockfile"),
            "Source: pylock.toml | Method: resolved_lockfile",
        ),
        (
            LockOrigin("requirements.txt", "pinned_requirements"),
            "Source: requirements.txt | Method: pinned_requirements",
        ),
        (
            LockOrigin("uv.lock", "resolved_lockfile", "poetry.lock"),
            "Source: uv.lock | Method: resolved_lockfile"
            " | Note: supersedes poetry.lock",
        ),
    ],
)
def test_lock_seed_text_is_frozen(origin: LockOrigin, text: str) -> None:
    """The seed text, as literals: an id input, changed only as a deliberate
    id break. The provenance string has the same text today."""
    assert lock_seed_text(origin) == text
    assert lock_provenance(origin) == text


@pytest.mark.parametrize(("files", "origin", "expected"), _ROUTE_PARAMS)
def test_document_id_pinned_through_each_lock_reader(
    tmp_path: Path, files: dict[str, str], origin: LockOrigin, expected: str
) -> None:
    """Each real lock reader records its origin and yields today's id."""
    root = _write(tmp_path / "proj", files)
    metadata, _config, _path = read_project(root)
    assert metadata.locked_dependencies_origin == origin
    assert metadata.provenance["locked_dependencies"] == lock_provenance(origin)
    assert project_document_id(root) == expected


@pytest.mark.parametrize(("files", "origin", "expected"), _ROUTE_PARAMS)
def test_rewording_the_provenance_keeps_the_document_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    files: dict[str, str],
    origin: LockOrigin,
    expected: str,
) -> None:
    """The provenance string a reader writes is no id input."""
    monkeypatch.setattr(
        project_module,
        "lock_provenance",
        lambda origin: f"Source: {origin.source} | Technique: lock, reworded",
    )
    root = _write(tmp_path / "proj", files)
    metadata, _config, _path = read_project(root)
    # Not vacuous: the text did change.
    assert metadata.provenance["locked_dependencies"] != lock_provenance(origin)
    assert project_document_id(root) == expected


def test_seed_of_a_caller_built_metadata_is_its_provenance_string() -> None:
    """Without an origin the provenance string seeds as given; with one,
    the origin does and the string is not read."""
    by_hand = ProjectMetadata(
        name="demo", provenance={"locked_dependencies": "Source: my lock"}
    )
    assert by_hand.locked_dependencies_seed() == "Source: my lock"
    assert ProjectMetadata(name="demo").locked_dependencies_seed() is None

    origin = LockOrigin("uv.lock", "resolved_lockfile")
    by_hand.record_lock_origin(origin)
    by_hand.provenance["locked_dependencies"] = "Source: reworded"
    assert by_hand.locked_dependencies_seed() == lock_seed_text(origin)


def test_merge_keeps_the_origin_with_its_provenance() -> None:
    """The origin follows ``provenance["locked_dependencies"]``: a primary
    that declares the lock by hand is not given the secondary's origin, and
    a primary with no lock takes the secondary's."""
    read = ProjectMetadata(name="demo", locked_dependencies=["idna==3.7"])
    read.record_lock_origin(LockOrigin("uv.lock", "resolved_lockfile"))
    by_hand = ProjectMetadata(
        name="demo", provenance={"locked_dependencies": "Source: my lock"}
    )

    kept = merge_project_metadata(by_hand, read)
    assert kept.locked_dependencies_origin is None
    assert kept.locked_dependencies_seed() == "Source: my lock"

    filled = merge_project_metadata(ProjectMetadata(name="demo"), read)
    assert filled.locked_dependencies_origin == read.locked_dependencies_origin
    assert filled.locked_dependencies_seed() == read.locked_dependencies_seed()
