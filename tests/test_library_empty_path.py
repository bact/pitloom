# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A library entry given an empty input path raises ``input-not-found``,
as ``os.stat("")`` says, and reads nothing of the current directory that
``Path("")`` would name. An empty ``output_path`` or ``id_registry`` is
``option-invalid`` (``non-empty``), as the CLI's ``-o ""`` is.

See also: tests/cli/test_empty_path.py (every command).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pitloom._sbom_io import write_sbom_output
from pitloom.assemble import (
    enrich_model,
    generate,
    generate_env_sbom,
    generate_git_sbom,
    generate_merged_sbom,
    generate_model_sbom,
    generate_project_sbom,
    generate_pypi_sbom,
    generate_wheel_sbom,
)
from pitloom.core.given_path import TypedPath
from pitloom.embed import embed_wheel_sbom
from pitloom.messages import CodedFileNotFoundError, CodedValueError, code_of
from pitloom.messages.targets import (
    MODEL_FILE_KIND,
    input_exists,
    refuse_empty_input,
)

pytestmark = pytest.mark.platform

_NPY = (
    Path(__file__).parent / "fixtures" / "aimodels" / "numpy" / "example-model-v1.npy"
)


# pylint: disable-next=too-few-public-methods
class _Spelt:
    """An ``os.PathLike`` spelling *text* as it is (``TypedPath("")`` is
    ``.``)."""

    def __init__(self, text: str) -> None:
        self.text = text

    def __fspath__(self) -> str:
        return self.text


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


def _no_fetch(url: str) -> None:
    raise AssertionError(f"fetched {url}")


_OUTPUT_ENTRIES: list[tuple[str, Callable[..., Any]]] = [
    ("wheel", lambda **kw: generate_wheel_sbom("x-1-py3-none-any.whl", **kw)),
    ("model", lambda **kw: generate_model_sbom("x.gguf", **kw)),
    ("enrich", lambda **kw: enrich_model("x.gguf", **kw)),
    ("project", lambda **kw: generate_project_sbom("x", **kw)),
    ("generate", lambda **kw: generate("x", **kw)),
    ("merged", lambda **kw: generate_merged_sbom("x", **kw)),
    ("env", generate_env_sbom),
    ("embed", lambda **kw: embed_wheel_sbom("x-1-py3-none-any.whl", **kw)),
    ("write", lambda **kw: write_sbom_output("{}", **kw)),
    (
        "git",
        lambda **kw: generate_git_sbom("https://127.0.0.1:9/o/r.git", **kw),
    ),
    (
        "pypi",
        lambda **kw: generate_pypi_sbom(
            "https://pypi.org/project/x/1/", check_url=_no_fetch, **kw
        ),
    ),
]


@pytest.mark.parametrize(
    "entry", [e for _, e in _OUTPUT_ENTRIES], ids=[i for i, _ in _OUTPUT_ENTRIES]
)
def test_library_empty_output_path(
    entry: Callable[..., Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Refused first, before the input is looked at or anything written."""
    monkeypatch.chdir(tmp_path)
    with pytest.raises(CodedValueError) as caught:
        entry(output_path="")
    assert code_of(caught.value) == "option-invalid"
    assert (
        str(caught.value) == "output_path: must be a non-empty string, got a string ''"
    )
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    ("given", "got"),
    [("", "a string ''"), (_Spelt(""), "a value of type _Spelt")],
    ids=["str", "pathlike"],
)
@pytest.mark.parametrize(
    ("entry", "target"),
    [(generate_project_sbom, "."), (generate_model_sbom, str(_NPY))],
    ids=["project", "model"],
)
def test_library_empty_id_registry(
    entry: Callable[..., Any],
    target: str,
    given: object,
    got: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "pyproject.toml").write_bytes(b'[project]\nname = "p"\nversion = "1"\n')
    monkeypatch.chdir(tmp_path)
    with pytest.raises(CodedValueError) as caught:
        entry(target, output_path=Path("o.json"), id_registry=given)
    assert code_of(caught.value) == "option-invalid"
    assert str(caught.value) == f"id_registry: must be a non-empty string, got {got}"
    assert not (tmp_path / "o.json").exists()


def test_config_empty_id_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``id-registry = ""`` would name the configuration's own directory."""
    (tmp_path / "pyproject.toml").write_bytes(
        b'[project]\nname = "p"\nversion = "1"\n[tool.pitloom]\nid-registry = ""\n'
    )
    monkeypatch.chdir(tmp_path)
    with pytest.raises(CodedValueError) as caught:
        generate_project_sbom(".", output_path=Path("o.json"))
    assert code_of(caught.value) == "config-invalid"
    assert "id-registry" in str(caught.value)
    assert "non-empty" in str(caught.value)
