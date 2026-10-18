# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The same input gives the same G7 result on every surface."""

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


def _baseline_outcomes(tmp: Path, sbom: str, standard: str) -> dict[str, str]:
    path = tmp / "baseline.spdx3.json"
    path.write_text(sbom, encoding="utf-8")
    return outcomes(path, standard=standard)


def test_the_hook_differs_from_the_source_sbom_only_by_built_time(
    tmp_path: Path,
) -> None:
    """The allowance above is exact: without it the shapes differ, with it not."""
    root = _project("hatchling")(tmp_path)
    source = PROJECT_SURFACES["library"](root, tmp_path, pytest.MonkeyPatch())
    built = hook_surface(root, tmp_path, pytest.MonkeyPatch())
    assert _shape(built) != _shape(source)
    assert _shape(built, {"builtTime"}) == _shape(source)
