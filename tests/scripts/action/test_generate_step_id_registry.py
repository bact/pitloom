# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the "Generate SBOM" step's ``id-registry``/
``update-id-registry`` inputs, against a stub ``loom`` -- split out of
``test_generate_step.py`` (502 lines, over this repo's file-size
guidance) to keep both files under it.

See also: :mod:`tests.scripts.action.test_generate_step` (the rest of
this step's tests; both modules share the ``generate`` fixture and
wheel-building helpers from
:mod:`tests.scripts.action._generate_step_shared`).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from tests.scripts.action._generate_step_shared import (
    EMBED_STDOUT,
    _make_wheel,
    _Result,
)
from tests.scripts.action._generate_step_shared import (  # noqa: F401
    generate_fixture as generate_fixture,
)


@pytest.mark.parametrize("mode", ["project", "model", "embed-wheel"])
def test_id_registry_is_passed_on_every_mode(
    generate: Callable[..., _Result], tmp_path: Path, mode: str
) -> None:
    """``id-registry`` becomes ``--id-registry FILE`` whatever the mode --
    loom itself decides whether it has any effect (e.g. a Hugging Face
    model resolved via "model"); empty passes nothing."""
    env: dict[str, str] = {}
    if mode == "model":
        env["PL_MODEL"] = "m.safetensors"
    elif mode == "embed-wheel":
        _make_wheel(tmp_path / "p-1.whl")
        env.update(PL_EMBED_WHEEL=str(tmp_path / "*.whl"), LOOM_STDOUT=EMBED_STDOUT)

    assert "--id-registry" not in generate(**env).loom_args

    result = generate(PL_ID_REGISTRY="loom-id-registry.json", **env)
    index = result.loom_args.index("--id-registry")
    assert result.loom_args[index + 1] == "loom-id-registry.json"

    # A path with a space stays one argument, as for PL_CONFIG above.
    result = generate(PL_ID_REGISTRY="ci dir/loom-id-registry.json", **env)
    index = result.loom_args.index("--id-registry")
    assert result.loom_args[index + 1] == "ci dir/loom-id-registry.json"


@pytest.mark.parametrize("mode", ["project", "model", "embed-wheel"])
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("true", ["--update-id-registry"]),
        ("false", ["--no-update-id-registry"]),
        # Neither "true" nor "false": silently dropped, same as an
        # out-of-range extract-file-header value -- the step never
        # validates a tri-state input itself, only loom does.
        ("maybe", []),
    ],
)
def test_update_id_registry_is_passed_on_every_mode(
    generate: Callable[..., _Result],
    tmp_path: Path,
    mode: str,
    value: str,
    expected: list[str],
) -> None:
    env: dict[str, str] = {}
    if mode == "model":
        env["PL_MODEL"] = "m.safetensors"
    elif mode == "embed-wheel":
        _make_wheel(tmp_path / "p-1.whl")
        env.update(PL_EMBED_WHEEL=str(tmp_path / "*.whl"), LOOM_STDOUT=EMBED_STDOUT)

    result = generate(PL_UPDATE_ID_REGISTRY=value, **env)
    for flag in ("--update-id-registry", "--no-update-id-registry"):
        assert (flag in result.loom_args) == (flag in expected)
