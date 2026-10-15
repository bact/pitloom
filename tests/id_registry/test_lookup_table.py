# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Every surface looks the registry up under the type and gate the design's
lookup table gives it (id-registry-v3 section 7), so a swapped type or gate
fails here and not as a silently missed id.

See also: tests/id_registry/test_session.py (the session's own claim rules),
tests/id_registry/test_surfaces.py (registry declaration per surface).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from unittest.mock import patch

import pytest

from pitloom import loom
from pitloom.assemble import (
    enrich_model,
    generate_model_sbom,
    generate_project_sbom,
    generate_wheel_sbom,
)
from pitloom.id_registry import (
    AI_PACKAGE_TYPE,
    FILE_TYPE,
    PACKAGE_TYPE,
    IdRegistry,
)
from tests._wheel_models import safetensors_bytes, write_model_wheel
from tests.cli.shared import SAFETENSORS_FIXTURE

_Lookup = tuple[str, bool, tuple[str, ...]]  # (type, gated by sha256, names)
_MODEL = "tiny.safetensors"


def _registry_file(tmp_path: Path) -> Path:
    path = tmp_path / "ids.json"
    IdRegistry.new("demo").save(path)
    return path


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / "demo").mkdir(parents=True)
    (root / "demo" / "__init__.py").write_bytes(b"x = 1\n")
    (root / "demo" / _MODEL).write_bytes(safetensors_bytes())
    (root / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["hatchling"]\n'
        'build-backend = "hatchling.build"\n'
        '[project]\nname = "demo"\nversion = "1.0.0"\n'
        'requires-python = ">=3.10"\n',
        encoding="utf-8",
    )
    return root


def _run_project(tmp_path: Path, _mp: pytest.MonkeyPatch) -> None:
    generate_project_sbom(
        _project(tmp_path),
        creation_metadata=None,
        id_registry=_registry_file(tmp_path),
    )


def _run_model(tmp_path: Path, _mp: pytest.MonkeyPatch) -> None:
    generate_model_sbom(SAFETENSORS_FIXTURE, id_registry=_registry_file(tmp_path))


def _run_enrich(tmp_path: Path, _mp: pytest.MonkeyPatch) -> None:
    enrich_model(SAFETENSORS_FIXTURE, id_registry=_registry_file(tmp_path))


def _run_wheel(tmp_path: Path, _mp: pytest.MonkeyPatch) -> None:
    wheel = write_model_wheel(
        tmp_path / "dist", {f"demo/{_MODEL}": safetensors_bytes()}
    )
    generate_wheel_sbom(wheel, id_registry=_registry_file(tmp_path))


def _run_loom(tmp_path: Path, mp: pytest.MonkeyPatch) -> None:
    """One run: ``set_model`` plus the generating script's own file."""
    mp.chdir(tmp_path)
    (tmp_path / "script.py").write_text("print('hi')\n", encoding="utf-8")
    registry = IdRegistry.load(_registry_file(tmp_path))
    with patch(
        "pitloom._loom_active_run._get_caller_script_path", return_value="script.py"
    ):
        with loom.run(tmp_path / "frag.json", id_registry=registry):
            loom.set_model("m")


def _observe(
    run: Callable[[Path, pytest.MonkeyPatch], None],
    tmp_path: Path,
    mp: pytest.MonkeyPatch,
) -> list[_Lookup]:
    """Run *run* with ``IdRegistry.lookup`` spied; return its calls, sorted.

    Names are kept raw: every key the registry stores is ``/``-separated
    (``id generate`` writes ``as_posix()``), so a ``\\`` a surface passes on
    Windows is a miss, not a spelling to normalise away. A wheel's raw
    archive name is the one legitimate ``\\``, and these wheels have none.
    """
    with patch.object(IdRegistry, "lookup", autospec=True, return_value=None) as spy:
        run(tmp_path, mp)
    return sorted(
        (call.args[1], call.kwargs["sha256"] is not None, tuple(call.args[2]))
        for call in spy.call_args_list
    )


_MODULE_FILE = (FILE_TYPE, True, ("demo/__init__.py",))
_DIRECTORY = (FILE_TYPE, False, ("demo",))
_MODEL_FILE = (FILE_TYPE, True, (f"demo/{_MODEL}",))
_MODEL_PACKAGE = (AI_PACKAGE_TYPE, False, (f"demo/{_MODEL}", "tiny"))
_PACKAGE = (PACKAGE_TYPE, False, ("demo",))

#: Design section 7, one row per caller: the (type, gated by sha256, names)
#: each surface asks ``IdRegistry.lookup`` for.
_TABLE: dict[str, tuple[Callable[..., None], list[_Lookup]]] = {
    "project": (
        _run_project,
        [_DIRECTORY, _MODULE_FILE, _MODEL_FILE, _MODEL_PACKAGE, _PACKAGE],
    ),
    "wheel-with-model": (
        _run_wheel,
        [_DIRECTORY, _MODEL_FILE, _MODEL_PACKAGE, _PACKAGE],
    ),
    "model": (_run_model, [(AI_PACKAGE_TYPE, False, ("whisper-tiny-random",))]),
    "enrich": (_run_enrich, [(AI_PACKAGE_TYPE, False, ("whisper-tiny-random",))]),
    "loom-script-and-model": (
        _run_loom,
        [
            (AI_PACKAGE_TYPE, False, ("m",)),
            (FILE_TYPE, True, ("script.py",)),
        ],
    ),
}


@pytest.mark.parametrize("surface", list(_TABLE))
def test_lookup_type_gate_and_names_per_surface(
    surface: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run, expected = _TABLE[surface]

    observed = _observe(run, tmp_path, monkeypatch)

    assert observed == sorted(expected)
    # Only a file's content identifies it: nothing else is sha256-gated.
    assert all(type_name == FILE_TYPE for type_name, gated, _ in observed if gated)
