# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``generate()`` hands every delegate every parameter, with the caller's value.

``pitloom.assemble.generate`` is the dispatcher behind ``loom generate`` and
the library's one-call entry point. Each of its five branches (env, wheel,
Hugging Face, model file, project) forwards its arguments through its own
hand-written keyword list, so any one branch can drop or hardcode a
parameter while the others keep it -- the silent-drop defect class the
configuration cascade exists to prevent, one layer up from it.

See also:
- :mod:`tests.assemble.test_config_cascade_drift` for the same guarantee one
  layer down, from each generator into the assemblers.
- :mod:`tests.core.generator.test_generator_misc` for ``generate()``'s
  target classification and no-effect warnings.
"""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pitloom import assemble
from pitloom.assemble import (
    generate,
    generate_env_sbom,
    generate_model_sbom,
    generate_project_sbom,
    generate_wheel_sbom,
)
from pitloom.core.build_options import BuildOptions
from pitloom.core.config import PitloomConfig
from pitloom.core.creation import CreationMetadata
from pitloom.core.provenance import ProvenanceConfig

from ..conftest import _make_wheel

# One distinctive value per forwarded parameter: each differs from the
# parameter's own default, so a hardcoded or dropped argument cannot
# coincide with it. Keyed by name, since generate() and every delegate
# spell these identically.
_SENTINELS: dict[str, Any] = {
    "output_path": Path("sentinel-out.spdx3.json"),
    "creation_metadata": CreationMetadata(creation_comment="sentinel-comment"),
    "pretty": True,
    "describe_relationship": True,
    "id_registry": "sentinel-registry.json",
    "provenance": ProvenanceConfig(max_source_metadata_bytes=4321),
    "offline": True,
    "content_type_method": "extension",
    "update_id_registry": False,
    "max_source_metadata_bytes": 4321,
    "pitloom_config": PitloomConfig(creation_comment="sentinel-config"),
    # Project/model-only parameters.
    "enrich": True,
    "extract_file_header": False,
    "scan_model_usage": True,
    "content_type": True,
    "use_lockfile": False,
    "build_options": BuildOptions(timeout=4321),
}


def _assert_forwards_every_parameter(
    delegate: Callable[..., object],
    called: dict[str, object],
    skip: set[str] | None = None,
) -> set[str]:
    """``generate()`` must hand this delegate every parameter it names, with
    the caller's own value.

    Asserting on one key only proves routing, not forwarding: dropping any
    single ``x=x`` line from the dispatch below still passes such a check,
    which is how ``content_type_method`` could go missing on the very
    branches this matrix exists to protect. Checking the *value* as well is
    what catches the other half -- a parameter forwarded as a hardcoded
    constant rather than the caller's choice. Reading the delegate's real
    signature means a parameter added to it later cannot be forgotten here
    either.

    Returns the sentinel kwargs to pass to ``generate()``.
    """
    expected = set(inspect.signature(delegate).parameters) - (skip or set())
    assert expected <= set(_SENTINELS), (
        f"{delegate.__name__}() gained {sorted(expected - set(_SENTINELS))}; "
        f"add a distinctive value to _SENTINELS"
    )
    missing = expected - set(called)
    assert not missing, f"generate() never forwarded {sorted(missing)}"
    wrong = {
        name: (called[name], _SENTINELS[name])
        for name in expected
        if called[name] != _SENTINELS[name]
    }
    assert not wrong, f"generate() forwarded (got, expected): {wrong}"
    return expected


def _sentinels_for(delegate: Callable[..., object], skip: set[str]) -> dict[str, Any]:
    """The sentinel kwargs ``generate()`` should be called with."""
    names = set(inspect.signature(delegate).parameters) - skip
    return {name: _SENTINELS[name] for name in names if name in _SENTINELS}


@pytest.mark.parametrize("target", ["env", "environment", "--env"])
def test_generate_dispatches_env_target(
    target: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """generate() recognises every "env" spelling and dispatches to
    generate_env_sbom() rather than treating it as a project path."""
    called: dict[str, object] = {}

    # wraps() gives the fake the real signature, so generate() filters
    # exactly what it would for the real delegate.
    @functools.wraps(generate_env_sbom)
    def _fake_generate_env_sbom(**kwargs: object) -> str:
        called.update(kwargs)
        return "env-sbom"

    monkeypatch.setattr(assemble, "generate_env_sbom", _fake_generate_env_sbom)
    assert generate(target, **_sentinels_for(generate_env_sbom, set())) == "env-sbom"
    _assert_forwards_every_parameter(generate_env_sbom, called)


def test_generate_forwards_every_wheel_parameter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The wheel branch's counterpart to the env check above."""
    called: dict[str, object] = {}

    @functools.wraps(generate_wheel_sbom)
    def _fake_generate_wheel_sbom(_target: str, **kwargs: object) -> str:
        called.update(kwargs)
        return "wheel-sbom"

    monkeypatch.setattr(assemble, "generate_wheel_sbom", _fake_generate_wheel_sbom)
    wheel_path = _make_wheel(tmp_path, "forward-pkg", "1.0.0")
    # wheel_path arrives positionally, so it is not in kwargs.
    skip = {"wheel_path"}
    sentinels = _sentinels_for(generate_wheel_sbom, skip)
    assert generate(wheel_path, **sentinels) == "wheel-sbom"
    _assert_forwards_every_parameter(generate_wheel_sbom, called, skip=skip)


def _project_target(tmp_path: Path) -> str:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "forward-pkg"\nversion = "1.0.0"\n', encoding="utf-8"
    )
    return str(tmp_path)


def _model_file_target(tmp_path: Path) -> str:
    model = tmp_path / "model.safetensors"
    model.write_bytes(b"\0")
    return str(model)


# (target builder, delegate attribute, the real delegate, parameters that
# generate() deliberately does not forward). generate() never pre-supplies
# project_metadata; generate_project_sbom() reads it from the target. The
# first positional parameter of each delegate is the target itself.
_BRANCHES = [
    pytest.param(
        _project_target,
        "generate_project_sbom",
        generate_project_sbom,
        {"project_target", "project_metadata"},
        id="project",
    ),
    pytest.param(
        _model_file_target,
        "generate_model_sbom",
        generate_model_sbom,
        {"source"},
        id="model-file",
    ),
    pytest.param(
        lambda _tmp: "https://huggingface.co/example-org/example-model",
        "generate_model_sbom",
        generate_model_sbom,
        {"source"},
        id="huggingface",
    ),
]


@pytest.mark.parametrize(("make_target", "attribute", "delegate", "skip"), _BRANCHES)
def test_generate_forwards_every_parameter_on_the_other_branches(
    make_target: Callable[[Path], str],
    attribute: str,
    delegate: Callable[..., object],
    skip: set[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The project, model-file and Hugging Face branches get the same
    value-level check as env and wheel -- each dispatches through its own
    hand-written argument list, so each can drop a parameter on its own."""
    called: dict[str, object] = {}

    @functools.wraps(delegate)
    def _fake(_target: object, **kwargs: object) -> str:
        called.update(kwargs)
        return "delegated"

    monkeypatch.setattr(assemble, attribute, _fake)
    target = make_target(tmp_path)
    assert generate(target, **_sentinels_for(delegate, skip)) == "delegated"
    _assert_forwards_every_parameter(delegate, called, skip=skip)
