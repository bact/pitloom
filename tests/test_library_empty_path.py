# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A library entry given an empty input path raises ``input-not-found``,
as ``os.stat("")`` says, and reads nothing of the current directory that
``Path("")`` would name. An empty ``output_path``, ``id_registry``
(anywhere: a keyword, ``PitloomConfig``, ``IdRegistry.load``),
``pitloom_config``, ``sbom_path``, ``sbom_basename``, ``sbom_filename``,
``project_dir`` or registry path (``IdRegistry`` ``path``, ``project_root``,
``generate()``'s paths) is ``option-invalid`` (``non-empty``), as the CLI's
``-o ""`` is.

See also: tests/cli/test_empty_path.py (every command).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest

from pitloom._sbom_io import write_sbom_output
from pitloom._wheel_sbom_location import find_embedded_sbom
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
    generate_wheel_sbom_with_metadata,
)
from pitloom.core.config import PitloomConfig
from pitloom.core.given_path import TypedPath
from pitloom.embed import embed_wheel_sbom
from pitloom.id_registry import IdRegistry
from pitloom.messages import CodedFileNotFoundError, CodedValueError, code_of
from pitloom.messages.targets import (
    MODEL_FILE_KIND,
    input_exists,
    refuse_empty_input,
)
from tests.argument_errors import enter_loom_run

pytestmark = pytest.mark.platform

_NPY = (
    Path(__file__).parent / "fixtures" / "aimodels" / "numpy" / "example-model-v1.npy"
)
#: A wheel that is not there: an empty option is refused before it is read.
_WHEEL = Path("gone-1.0-py3-none-any.whl")


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
    (generate_model_sbom, "model file not found: ''"),
    (enrich_model, "model file not found: ''"),
    (generate_project_sbom, "project path not found: ''"),
    (generate, "target not found: ''"),
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
@pytest.mark.parametrize(
    ("call", "said"),
    [
        (find_embedded_sbom, "wheel file not found: ''"),
        (
            lambda given: IdRegistry.new("p").import_sbom(given),
            "SBOM file not found: ''",
        ),
        (
            lambda given: IdRegistry.new("p").generate([given], Path(".")),
            "PATH not found: ''",
        ),
    ],
    ids=["find-embedded-sbom", "registry-import", "registry-generate"],
)
def test_library_empty_input_without_output(
    call: Callable[[Any], object],
    said: str,
    given: str | Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Not read as the current directory (``FILE=.: not a .whl file``)."""
    monkeypatch.chdir(tmp_path)
    with pytest.raises(CodedFileNotFoundError) as caught:
        call(given)
    assert code_of(caught.value) == "input-not-found"
    assert str(caught.value) == said


@pytest.mark.parametrize("given", ["   ", " \t"], ids=["spaces", "tab"])
def test_generate_blank_target_is_not_found(
    given: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A blank target is named as given, as the CLI names it, though
    stripping it (for a URL or ``env``) leaves the empty spelling."""
    (tmp_path / "pyproject.toml").write_bytes(b'[project]\nname = "p"\nversion = "1"\n')
    monkeypatch.chdir(tmp_path)
    with pytest.raises(CodedFileNotFoundError) as caught:
        generate(given, output_path=tmp_path / "out.json")
    assert code_of(caught.value) == "input-not-found"
    assert str(caught.value) == f"target not found: {given!r}"
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


#: An empty value of an option given to the library (the twin of a flag
#: argparse refuses): the call -> what the line names.
_EMPTY_OPTIONS: list[tuple[str, Callable[[str | Path], object], str]] = [
    ("registry-load", IdRegistry.load, "path"),
    (
        "config-registry",
        lambda given: PitloomConfig(id_registry=given),  # type: ignore[arg-type]
        "PitloomConfig.id_registry",
    ),
    (
        "config-basename",
        lambda given: PitloomConfig(sbom_basename=given),  # type: ignore[arg-type]
        "PitloomConfig.sbom_basename",
    ),
    (
        "loom-config",
        lambda given: enter_loom_run(pitloom_config=given),
        "pitloom_config",
    ),
    (
        "embed-sbom",
        lambda given: embed_wheel_sbom(_WHEEL, sbom_path=given),
        "sbom_path",
    ),
    (
        "embed-basename",
        lambda given: embed_wheel_sbom(_WHEEL, sbom_basename=cast(str, given)),
        "sbom_basename",
    ),
    (
        "wheel-sbom-filename",
        lambda given: find_embedded_sbom(_WHEEL, cast(str, given)),
        "sbom_filename",
    ),
    (
        "embed-project-dir",
        lambda given: embed_wheel_sbom(_WHEEL, project_dir=given),
        "project_dir",
    ),
    (
        "wheel-project-dir",
        lambda given: generate_wheel_sbom(_WHEEL, project_dir=given),
        "project_dir",
    ),
    (
        "wheel-metadata-project-dir",
        lambda given: generate_wheel_sbom_with_metadata(_WHEEL, project_dir=given),
        "project_dir",
    ),
    (
        "pypi-wheel-project-dir",
        lambda given: generate_wheel_sbom(
            "https://pypi.org/project/x/1/", check_url=_no_fetch, project_dir=given
        ),
        "project_dir",
    ),
    (
        "generate-project-dir",
        # A model target: no delegate of generate() checks project_dir.
        lambda given: generate("m.gguf", output_path=Path("o.json"), project_dir=given),
        "project_dir",
    ),
    (
        "project-project-dir",
        lambda given: generate_project_sbom(".", project_dir=given),
        "project_dir",
    ),
    ("registry-new", lambda given: IdRegistry.new("p", path=cast(Path, given)), "path"),
    (
        "registry-root",
        lambda given: IdRegistry.new("p", project_root=cast(Path, given)),
        "project_root",
    ),
    (
        "registry-generate-exclude",
        lambda given: IdRegistry.new("p").generate(
            [Path("x")], Path("."), exclude=cast(Path, given)
        ),
        "exclude",
    ),
    (
        "registry-generate-root",
        lambda given: IdRegistry.new("p").generate([Path("x")], cast(Path, given)),
        "project_root",
    ),
]


#: The cases of :data:`_EMPTY_OPTIONS` that take a file name, not a path:
#: no ``TypedPath`` spelling.
_NAMES = {"config-basename", "embed-basename", "wheel-sbom-filename"}


@pytest.mark.parametrize(
    ("call", "name", "given"),
    [
        pytest.param(call, name, given, id=f"{case}-{kind}")
        for case, call, name in _EMPTY_OPTIONS
        for kind, given in (("str", ""), ("typed", TypedPath("")))
        if kind == "str" or case not in _NAMES
    ],
)
def test_an_empty_option_is_invalid(
    call: Callable[[str | Path], object],
    name: str,
    given: str | Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Refused as the option's own error, as the CLI's ``--id-registry ''``,
    ``--config ''``, ``--sbom ''``, ``--sbom-basename ''`` and
    ``--sbom-filename ''`` are: never read as ``.``, never the default
    name, and nothing looked at (the wheel named is not there)."""
    monkeypatch.chdir(tmp_path)
    with pytest.raises(CodedValueError) as caught:
        call(given)
    assert code_of(caught.value) == "option-invalid"
    assert str(caught.value) == f"{name}: must be a non-empty string, got a string ''"
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("default", [None, "r.json"], ids=["no-default", "default"])
@pytest.mark.parametrize("given", ["", TypedPath("")], ids=["str", "typed"])
def test_id_registry_save_empty_is_option_invalid(
    given: str | Path,
    default: str | None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``IdRegistry.save("")`` writes nothing, not even to its own
    :attr:`~pitloom.id_registry.IdRegistry.path`: an empty path is never
    "the default"."""
    monkeypatch.chdir(tmp_path)
    path = None if default is None else tmp_path / default
    registry = IdRegistry(namespace="https://example.org/ns/", path=path)
    with pytest.raises(CodedValueError) as caught:
        registry.save(given)
    assert code_of(caught.value) == "option-invalid"
    assert str(caught.value) == ("path: must be a non-empty string, got a string ''")
    assert not list(tmp_path.iterdir())
