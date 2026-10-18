# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The same input gives the same checker result (G7, CISA 2026, FSCT 2024)
and the same names, versions, identifiers and hashes on every surface."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from tests._wheel_models import safetensors_bytes, write_model_wheel
from tests.conformance.g7ai_shared import (
    AIMODELS,
    BACKENDS,
    outcomes,
    write_project,
)
from tests.conformance.g7ai_surfaces import (
    MODEL_SURFACES,
    PROJECT_SURFACES,
    WHEEL_SURFACES,
    Runner,
    hook_surface,
)

#: Every standard the checker reports on for Pitloom's SBOMs.
STANDARDS = ("g7ai", "cisa2026", "fsct3")

#: Elements about who made the SBOM, not about what it describes.
_CREATION = {"CreationInfo", "Tool", "Person", "Organization", "SoftwareAgent", "Agent"}


#: Properties a surface may add because of what it is: the build hook runs
#: during a build, so it records when the package was built; a source SBOM
#: has no build.
_SURFACE_ONLY = {"hook": {"builtTime"}}


def _shape(
    sbom: str, drop: set[str] | None = None
) -> list[tuple[str, tuple[str, ...]]]:
    """The element types and property names of *sbom*, ignoring who made it."""
    graph = json.loads(sbom)["@graph"]
    return sorted(
        (str(e["type"]), tuple(sorted(set(e) - (drop or set()))))
        for e in graph
        if e["type"] not in _CREATION
    )


#: Values a surface must not change: what the package is called, its version,
#: identifiers and hashes.
_VALUE_KEYS = ("name", "software_packageVersion", "software_packageUrl", "hashValue")


def _values(sbom: str) -> list[tuple[str, str, str]]:
    """The ``_VALUE_KEYS`` values of *sbom*'s elements and their hashes, ignoring
    who made it and the element ids (which differ by surface). An element's
    hashes are one value, each algorithm with its digest, in their order."""
    found: list[tuple[str, str, str]] = []
    for element in json.loads(sbom)["@graph"]:
        if element["type"] in _CREATION:
            continue
        found += [
            (str(element["type"]), k, str(element[k]))
            for k in _VALUE_KEYS
            if k in element
        ]
        hashes = [
            f"{method.get('algorithm')}:{method.get('hashValue')}"
            for method in element.get("verifiedUsing", [])
        ]
        if hashes:
            found.append((str(element["type"]), "verifiedUsing", " ".join(hashes)))
    return sorted(found)


def _model(_tmp: Path) -> Path:
    return AIMODELS / "safetensors/phi-tiny-random.safetensors"


def _project(backend: str) -> Callable[[Path], Path]:
    def build(tmp: Path) -> Path:
        root = tmp / "proj"
        root.mkdir()
        write_project(root, BACKENDS[backend])
        return root

    return build


def _wheel(tmp: Path) -> Path:
    return write_model_wheel(
        tmp / "dist",
        {"demo/__init__.py": b"x = 1\n", "demo/m.safetensors": safetensors_bytes()},
    )


CASES: list[tuple[str, Callable[[Path], Path], dict[str, Runner]]] = [
    ("model-safetensors", _model, MODEL_SURFACES),
    *[
        (
            f"proj-{b}",
            _project(b),
            PROJECT_SURFACES | ({"hook": hook_surface} if b == "hatchling" else {}),
        )
        for b in BACKENDS
    ],
    ("wheel", _wheel, WHEEL_SURFACES),
]


@pytest.mark.parametrize(
    ("name", "build", "surfaces"), CASES, ids=[c[0] for c in CASES]
)
def test_every_surface_gives_the_library_result(
    name: str,
    build: Callable[[Path], Path],
    surfaces: dict[str, Runner],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same outcome for every rule of every standard, and the same elements."""
    source = build(tmp_path)
    results: dict[str, str] = {}
    for surface, run in surfaces.items():
        scratch = tmp_path / f"out-{surface}"
        scratch.mkdir()
        results[surface] = run(source, scratch, monkeypatch)
    assert "library" in results
    baseline = results["library"]
    assert _shape(baseline), f"{name}: the library SBOM describes nothing"
    for surface, sbom in results.items():
        path = tmp_path / f"{surface}.spdx3.json"
        path.write_text(sbom, encoding="utf-8")
        for standard in STANDARDS:
            assert outcomes(path, standard=standard) == _baseline_outcomes(
                tmp_path, baseline, standard
            ), (surface, standard)
        drop = _SURFACE_ONLY.get(surface, set())
        assert _shape(sbom, drop) == _shape(baseline), surface
        assert _values(sbom) == _values(baseline), surface


def _baseline_outcomes(tmp: Path, sbom: str, standard: str) -> dict[str, str]:
    path = tmp / "baseline.spdx3.json"
    path.write_text(sbom, encoding="utf-8")
    return outcomes(path, standard=standard)


def _hashed(*hashes: tuple[str, str]) -> str:
    """A one-package SBOM whose ``verifiedUsing`` is *hashes*, in order."""
    verified = [{"algorithm": a, "hashValue": v} for a, v in hashes]
    graph = [{"type": "software_Package", "name": "m", "verifiedUsing": verified}]
    return json.dumps({"@graph": graph})


_BOTH = (("sha256", "ab" * 32), ("sha512", "cd" * 64))


@pytest.mark.parametrize(
    "changed",
    [
        _hashed(*_BOTH).replace('"m"', '"other"'),
        _hashed(*_BOTH).replace("ab" * 32, "00" * 32),
        _hashed(*_BOTH).replace("cd" * 64, "00" * 64),
        _hashed(_BOTH[0]),
        _hashed(*reversed(_BOTH)),
        _hashed(("sha512", "ab" * 32), _BOTH[1]),
    ],
    ids=[
        "name",
        "sha256-value",
        "sha512-value",
        "sha512-dropped",
        "order",
        "algorithm",
    ],
)
def test_values_differ_when_a_surface_writes_a_wrong_hash_or_name(
    changed: str,
) -> None:
    """Guard: the value comparison sees a changed name, either digest
    changed or dropped, the hashes reordered and a wrong algorithm."""
    assert _values(changed) != _values(_hashed(*_BOTH))


def test_the_hook_differs_from_the_source_sbom_only_by_built_time(
    tmp_path: Path,
) -> None:
    """The allowance above is exact: without it the shapes differ, with it not."""
    root = _project("hatchling")(tmp_path)
    source = PROJECT_SURFACES["library"](root, tmp_path, pytest.MonkeyPatch())
    built = hook_surface(root, tmp_path, pytest.MonkeyPatch())
    assert _shape(built) != _shape(source)
    assert _shape(built, {"builtTime"}) == _shape(source)
