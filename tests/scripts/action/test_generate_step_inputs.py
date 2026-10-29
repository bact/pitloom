# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the "Generate SBOM" step's inputs: each reaches the script
through the step's ``env:``, and the byte-cap inputs become their flags.

See also: :mod:`tests.scripts.action.test_generate_step` (the rest of this
step's tests; both modules share the ``generate`` fixture from
:mod:`tests.scripts.action._generate_step_shared`).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml

from tests.scripts.action._generate_step_shared import (
    EMBED_STDOUT,
    _generate_script,
    _make_wheel,
    _Result,
)

# Imported so pytest discovers the shared "generate" fixture here.
# The alias keeps ruff from merging this re-export into the import above.
# pylint: disable-next=unused-import,useless-import-alias
from tests.scripts.action._generate_step_shared import (  # noqa: F401
    generate_fixture as generate_fixture,
)


def test_every_variable_the_script_reads_comes_from_its_input(
    scripts_dir: Path,
) -> None:
    """``PL_X`` is set from the input ``x`` (lower case, ``-`` for ``_``):
    a variable missing from ``env:`` would read as empty, a silent no-op."""
    action_yml = scripts_dir.parent / "action.yml"
    action = yaml.safe_load(action_yml.read_text(encoding="utf-8"))
    (step,) = [s for s in action["runs"]["steps"] if s.get("id") == "generate"]
    read = set(re.findall(r"\$\{(PL_[A-Z_]+)", _generate_script(action_yml)))
    assert {"PL_MAX_MODEL_EXTRACT_BYTES", "PL_TRUST_WHEEL_MODEL"} <= read
    for name in read:
        given = name.removeprefix("PL_").lower().replace("_", "-")
        assert step["env"].get(name) == f"${{{{ inputs.{given} }}}}", name
        assert given in action["inputs"], name


@pytest.mark.parametrize("mode", ["project", "embed-wheel", "model"])
@pytest.mark.parametrize(
    ("env_name", "flag"),
    [
        ("PL_MAX_SOURCE_METADATA_BYTES", "--max-source-metadata-bytes"),
        ("PL_MAX_MODEL_EXTRACT_BYTES", "--max-model-extract-bytes"),
    ],
)
@pytest.mark.parametrize("value", ["", "4096", "0"])
def test_byte_cap_inputs_are_passed_verbatim(
    generate: Callable[..., _Result],
    tmp_path: Path,
    mode: str,
    env_name: str,
    flag: str,
    value: str,
) -> None:
    """A cap input becomes ``FLAG VALUE`` in every mode, an invalid one
    too: ``loom`` alone validates it and warns where it has no effect.
    Empty defers to the config and passes nothing."""
    env = {env_name: value}
    if mode == "embed-wheel":
        _make_wheel(tmp_path / "p-1.whl")
        env.update(PL_EMBED_WHEEL=str(tmp_path / "*.whl"), LOOM_STDOUT=EMBED_STDOUT)
    elif mode == "model":
        env["PL_MODEL"] = "m.safetensors"
    args = generate(**env).loom_args
    assert args[0] == mode
    tail = [args[i + 1] for i, arg in enumerate(args) if arg == flag]
    assert tail == ([value] if value else [])
