# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``loom model FILE`` and ``loom enrich FILE`` cut a model's lists and maps
to the same entries, with the same one ``WARNING:``, as a project scan of
that file does.

See also: :mod:`tests.extract.scanner.test_scanner_model_limits` (the cap
itself) and :mod:`docs/ai-model-scan-limits.md` (what is documented).
"""

# pylint: disable=missing-function-docstring,protected-access

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.assemble import _model_generator
from pitloom.assemble._model_generator import enrich_model, generate_model_sbom
from pitloom.core.ai_metadata import AiModelMetadata
from pitloom.core.project import ProjectFile
from pitloom.extract.ai_model.limits import MAX_MODEL_ENTRIES
from pitloom.extract.scanner_project import scan_project_for_ai_models
from tests._wheel_models import safetensors_bytes
from tests.warning_helpers import logged_warnings

_OVER = MAX_MODEL_ENTRIES + 500
_Built = tuple[Path, Callable[[AiModelMetadata], list[str]], list[str]]


def _npz(directory: Path) -> _Built:
    np = pytest.importorskip("numpy")
    path = directory / "m.npz"
    np.savez(path, **{f"a{i:04d}": np.zeros(1) for i in range(_OVER)})
    expected = [f"a{i:04d}" for i in range(MAX_MODEL_ENTRIES)]  # file order
    return path, lambda m: [str(i["name"]) for i in m.inputs], expected


def _safetensors(directory: Path) -> _Built:
    pytest.importorskip("safetensors")
    keys = [f"k{i:04d}" for i in range(_OVER)]
    path = directory / "m.safetensors"
    # Written in reverse: the kept ones are the smallest keys, not the first.
    path.write_bytes(safetensors_bytes(metadata=dict.fromkeys(keys[::-1], "v")))
    return path, lambda m: list(m.properties), keys[:MAX_MODEL_ENTRIES]


_BUILDERS = [_npz, _safetensors]
_SURFACES: dict[str, Callable[..., object]] = {
    "generate_model_sbom": generate_model_sbom,
    "enrich_model": enrich_model,
}


@pytest.mark.parametrize("surface", _SURFACES)
@pytest.mark.parametrize("build", _BUILDERS)
def test_a_model_file_is_capped_like_a_scan_with_one_warning(
    build: Callable[[Path], _Built],
    surface: str,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Regression: only the scans cut and announced; ``loom model`` kept
    1001 entries of the same file, silently."""
    path, kept, expected = build(tmp_path)
    # pylint: disable-next=unbalanced-tuple-unpacking
    (scanned,) = scan_project_for_ai_models(
        tmp_path,
        [ProjectFile(physical_path=path.name, distribution_path=path.name)],
        scan_usage=False,
        usage_hint=lambda: False,
    )
    (scan_message,) = logged_warnings(caplog)
    assert kept(scanned) == expected
    caplog.clear()

    local = _model_generator._read_local_model(path)
    assert kept(local) == expected
    assert local.provenance == scanned.provenance
    (local_message,) = logged_warnings(caplog)
    assert local_message.replace(str(path), path.name) == scan_message
    assert "more than 1000 entries in " in local_message

    caplog.clear()
    _SURFACES[surface](path, output_path=tmp_path / "out.json")
    (message,) = [m for m in logged_warnings(caplog) if "entries in" in m]
    assert message == local_message


@pytest.mark.parametrize("command", ["model", "enrich"])
def test_the_cli_names_the_model_as_it_was_given(
    command: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Regression: ``loom model``/``enrich`` resolved the path first, so its
    ``FILE=`` was absolute where a scan's is the one the user wrote."""
    (tmp_path / "models").mkdir()
    path, _, _ = _safetensors(tmp_path / "models")
    monkeypatch.chdir(tmp_path)
    given = Path("models") / path.name
    monkeypatch.setattr(
        sys, "argv", ["loom", command, str(given), "-o", str(tmp_path / "out.json")]
    )
    assert __main__.main() == 0
    (message,) = [m for m in logged_warnings(caplog) if "entries in" in m]
    assert f"FILE={given}:" in message
    assert str(tmp_path) not in message


@pytest.mark.parametrize("budget", [0, 10_000], ids=["no-budget", "budget"])
def test_the_annotation_counts_the_keys_over_the_cap(
    budget: int, tmp_path: Path
) -> None:
    """The keys the cap left out are counted, not named; a byte budget's
    dropped keys are named and counted with them."""
    path, _, _ = _safetensors(tmp_path)
    graph = json.loads(generate_model_sbom(path, max_source_metadata_bytes=budget))[
        "@graph"
    ]
    (statement,) = [
        json.loads(e["statement"])
        for e in graph
        if e.get("type") == "Annotation" and '"artifact-metadata"' in e["statement"]
    ]
    named = statement.get("truncatedKeys", [])
    assert bool(named) == bool(budget)
    assert statement["truncated"] is True
    assert statement["maxEntries"] == MAX_MODEL_ENTRIES
    assert statement["truncatedKeyCount"] == _OVER - MAX_MODEL_ENTRIES + len(named)
    assert len(statement["metadata"]) + statement["truncatedKeyCount"] == _OVER
