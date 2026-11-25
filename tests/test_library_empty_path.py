# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A library entry given an empty input path raises ``input-not-found``,
as ``os.stat("")`` says, and reads nothing of the current directory that
``Path("")`` would name.

See also: tests/cli/test_empty_path.py (every command).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble import (
    enrich_model,
    generate,
    generate_merged_sbom,
    generate_model_sbom,
    generate_project_sbom,
    generate_wheel_sbom,
)
from pitloom.core.given_path import TypedPath
from pitloom.embed import embed_wheel_sbom
from pitloom.messages import CodedFileNotFoundError, code_of
from pitloom.messages.targets import (
    MODEL_FILE_KIND,
    input_exists,
    refuse_empty_input,
)

pytestmark = pytest.mark.platform

_ENTRIES: list[tuple[Callable[..., Any], str]] = [
    (generate_wheel_sbom, "wheel file not found: ''"),
    (embed_wheel_sbom, "wheel file not found: ''"),
    (generate_model_sbom, "Model file not found: ''"),
    (enrich_model, "Model file not found: ''"),
    (generate_project_sbom, "project path not found: ''"),
    (generate, "project path not found: ''"),
    (generate_merged_sbom, "fragments directory not found: ''"),
]


@pytest.mark.parametrize("given", ["", TypedPath("")], ids=["str", "typed"])
@pytest.mark.parametrize(
    ("entry", "said"), _ENTRIES, ids=[e.__name__ for e, _ in _ENTRIES]
)
def test_library_empty_path(
    entry: Callable[..., Any],
    said: str,
    given: str | Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The current directory holds what ``.`` would read; nothing of it is."""
    (tmp_path / "pyproject.toml").write_bytes(b'[project]\nname = "p"\nversion = "1"\n')
    (tmp_path / "a.json").write_bytes(b"{}")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(CodedFileNotFoundError) as caught:
        entry(given, output_path=tmp_path / "out.json")
    assert code_of(caught.value) == "input-not-found"
    assert str(caught.value) == said
    assert not (tmp_path / "out.json").exists()


@pytest.mark.parametrize("given", ["", TypedPath("")], ids=["str", "typed"])
def test_probe_says_empty_is_not_there(given: str | Path) -> None:
    """The input probe: an empty spelling names nothing, though the path
    built from it (``.``) is a directory."""
    assert Path(given).is_dir()
    assert not input_exists(given)
    assert not input_exists(Path("."), shown=given)


def test_refuse_empty_input_checks_its_kind() -> None:
    """A kind no line names is a bug, even for a path that is not empty;
    the model kind and a non-empty path pass."""
    with pytest.raises(ValueError, match="not in INPUT_KINDS"):
        refuse_empty_input("x", "no such kind")
    refuse_empty_input("x", MODEL_FILE_KIND)
    refuse_empty_input(".", "wheel file")
