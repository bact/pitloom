# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""With ``-o -`` stdout is the SBOM itself: one JSON document, nothing
after it, so ``loom ... -o - | jq .`` works.

One case per leaf subcommand that takes ``--output`` -- the completeness
test fails when a new one has no case here.

See also: :mod:`tests.cli.test_cli_kv_stdout` (stdout for a written file).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.cli.parser import _build_parser
from tests.assemble.conftest import _make_dummy_wheel
from tests.assemble.embed_surfaces_shared import demo_project
from tests.cli.shared import SAFETENSORS_FIXTURE, fragments_dir
from tests.kv_helpers import info_kv


def _wheel(tmp_path: Path) -> str:
    return str(_make_dummy_wheel(tmp_path / "dist", "demo", "1.0.0"))


#: Leaf subcommand -> argv after ``loom``, before ``-o -``.
_CASES: dict[str, tuple[str, ...]] = {
    "generate": ("generate", "{project}", "--offline"),
    "project": ("project", "{project}", "--offline"),
    "wheel": ("wheel", "{wheel}", "--offline"),
    "wheel --embed": ("wheel", "{wheel}", "--embed", "--offline"),
    "embed-wheel": ("embed-wheel", "{wheel}", "--offline"),
    "model": ("model", str(SAFETENSORS_FIXTURE)),
    "enrich": ("enrich", str(SAFETENSORS_FIXTURE)),
    "env": ("env", "--offline"),
    "merge": ("merge", "{fragments}"),
}


def _output_commands() -> set[str]:
    """Every leaf subcommand of the real parser that takes ``--output``."""
    found: set[str] = set()

    def walk(parser: argparse.ArgumentParser, prefix: str) -> None:
        # pylint: disable-next=protected-access
        actions = parser._actions
        for action in actions:
            # pylint: disable-next=protected-access
            if isinstance(action, argparse._SubParsersAction):
                for name, child in action.choices.items():
                    walk(child, f"{prefix} {name}".strip())
            elif "--output" in action.option_strings:
                found.add(prefix)

    walk(_build_parser(), "")
    return found


def test_every_output_subcommand_has_a_case() -> None:
    """A new subcommand taking ``--output`` needs a case here."""
    assert {case.split(" --")[0] for case in _CASES} == _output_commands()


@pytest.mark.parametrize("case", sorted(_CASES))
def test_stdout_is_only_the_sbom(
    case: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Regression: a ``PITLOOM_SBOM_OUTPUT_PATH=-`` line (or any other data
    line) after the SBOM made stdout invalid JSON."""
    monkeypatch.chdir(tmp_path)
    targets = {"project": "", "wheel": "", "fragments": ""}
    argv = list(_CASES[case])
    if "{project}" in argv:
        targets["project"] = str(demo_project(tmp_path))
    if "{wheel}" in argv:
        targets["wheel"] = _wheel(tmp_path)
    if "{fragments}" in argv:
        targets["fragments"] = fragments_dir(tmp_path)
    argv = [arg.format(**targets) for arg in argv]
    monkeypatch.setattr(sys, "argv", ["loom", *argv, "-o", "-"])

    assert __main__.main() == 0

    captured = capsys.readouterr()
    assert "@graph" in json.loads(captured.out)  # raises on a line after it
    assert not (tmp_path / "-").exists()
    # The embed record moves to stderr, not away.
    embedded = info_kv(captured.err).get("SBOM", "")
    assert embedded.endswith(".spdx3.json") is ("embed" in case)
