# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The loom SDK's check of its callers' arguments
(:mod:`pitloom._loom_args`): a wrong type is a coded ``TypeError`` at the
call, an unknown ``dataset_type`` a coded ``ValueError``, and no fragment
is written.

See also: :mod:`tests.core.test_loom_sdk_lines` (the SDK's other lines).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pitloom import loom
from pitloom._loom_args import check_sdk_arguments
from pitloom._loom_dataset import _dataset_kind as dataset_kind_of
from pitloom.core.internal_error import InternalError
from pitloom.messages import code_of

_Call = Callable[[], object]


# pylint: disable-next=too-few-public-methods
class _Spelt:
    """An ``os.PathLike`` spelling *text* as it is."""

    def __init__(self, text: str) -> None:
        self.text = text

    def __fspath__(self) -> str:
        return self.text


#: The SDK as an untyped caller sees it.
_sdk: Any = loom


@pytest.fixture(name="project")
def _project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.txt").write_bytes(b"a")
    return tmp_path


def _hyperparameters_of_a_list() -> None:
    _sdk.set_model("m")
    _sdk.set_model_hyperparameters(["a"])


# Each refused call, the parameter its line names; the arguments as an
# untyped caller gives them.
_TYPE_CASES: list[tuple[str, _Call, str]] = [
    ("name-none", lambda: _sdk.set_model(None), "name"),
    ("path-int", lambda: _sdk.set_model("m", path=5), "path"),
    ("path-bytes", lambda: _sdk.set_model("m", path=b"m.bin"), "path"),
    ("type-bool", lambda: _sdk.set_model("m", model_type=True), "model_type"),
    ("dataset-int", lambda: _sdk.add_dataset(5), "name"),
    ("dataset-none", lambda: _sdk.add_dataset(None), "name"),
    ("croissant-int", lambda: _sdk.add_dataset("a.txt", croissant=5), "croissant"),
    ("hyper-list", _hyperparameters_of_a_list, "hyperparameters"),
    (
        "hyper-value",
        lambda: _sdk.set_model("m", hyperparameters={"lr": 0.1}),
        "hyperparameters",
    ),
    (
        "hyper-key",
        lambda: _sdk.set_model("m", hyperparameters={1: "a"}),
        "hyperparameters",
    ),
    (
        "prep-str",
        lambda: _sdk.add_output_dataset("o", data_preprocessing="tok"),
        "data_preprocessing",
    ),
    (
        "prep-int",
        lambda: _sdk.add_output_dataset("o", data_preprocessing=["tok", 5]),
        "data_preprocessing",
    ),
    (
        "licence-int",
        lambda: _sdk.add_dataset("a.txt", declared_license=5),
        "declared_license",
    ),
    (
        "inputs-str",
        lambda: _sdk.add_output_dataset("o", input_datasets="a.txt"),
        "input_datasets",
    ),
    (
        "inputs-nested",
        lambda: _sdk.add_output_dataset("o", input_datasets=[["a.txt"]]),
        "input_datasets",
    ),
    ("kind-int", lambda: _sdk.add_dataset("a.txt", 5), "dataset_type"),
    ("generated-str", lambda: _sdk.set_model("m", generated="y"), "generated"),
    ("use-name-none", lambda: _sdk.use_model(None), "name"),
    ("use-path-int", lambda: _sdk.use_model("m", path=5), "path"),
    ("pretty-str", lambda: _sdk.run("o.json", pretty="y"), "pretty"),
    ("pretty-int", lambda: _sdk.run("o.json", pretty=1), "pretty"),
    ("pretty-none", lambda: _sdk.run("o.json", pretty=None), "pretty"),
    (
        "creation-dict",
        lambda: _sdk.run("o.json", creation_metadata={}),
        "creation_metadata",
    ),
    ("registry-int", lambda: _sdk.run("o.json", id_registry=5), "id_registry"),
    ("policy-str", lambda: _sdk.run("o.json", credentials="x"), "credentials"),
]


@pytest.mark.parametrize(
    ("call", "parameter"),
    [pytest.param(c, p, id=i) for i, c, p in _TYPE_CASES],
)
def test_a_wrong_type_is_a_coded_type_error_at_the_call(
    project: Path, call: _Call, parameter: str
) -> None:
    out = project / "out.json"
    with pytest.raises(TypeError) as raised:
        with loom.run(out):
            call()
    assert code_of(raised.value) == "option-invalid"
    assert str(raised.value).startswith(f"loom SDK: {parameter}: must be ")
    assert not out.exists()


@pytest.mark.usefixtures("project")
def test_a_run_given_bytes_for_its_output_is_refused() -> None:
    with pytest.raises(TypeError) as raised:
        _sdk.run(b"out.json")
    assert code_of(raised.value) == "option-invalid"
    assert str(raised.value).startswith("loom SDK: output_file: must be a path")


@pytest.mark.platform
@pytest.mark.parametrize("given", ["", _Spelt("")], ids=["str", "pathlike"])
def test_a_run_given_an_empty_output_is_refused_at_the_call(
    project: Path, given: object
) -> None:
    """Not the current directory, and not an error at the run's exit."""
    with pytest.raises(ValueError) as raised:
        _sdk.run(given)
    assert code_of(raised.value) == "option-invalid"
    assert str(raised.value).startswith(
        "loom SDK: output_file: must be a non-empty string, got "
    )
    assert not list(project.glob("*.json"))


@pytest.mark.usefixtures("project")
def test_a_run_given_an_empty_registry_is_refused_at_the_call() -> None:
    """``option-invalid``, as an empty ``--id-registry`` is, not a registry
    file looked up as ``''``."""
    with pytest.raises(ValueError) as raised:
        _sdk.run("out.json", id_registry="")
    assert code_of(raised.value) == "option-invalid"
    assert str(raised.value).startswith(
        "loom SDK: id_registry: must be a non-empty string, got "
    )


@pytest.mark.platform
def test_an_empty_config_path_is_named_as_given(project: Path) -> None:
    """``option-invalid``, as ``--config ''`` is: an empty option, not the
    current directory ``Path("")`` reads it as."""
    with pytest.raises(ValueError) as raised:
        with loom.run(project / "out.json", pitloom_config=""):
            pass
    assert code_of(raised.value) == "option-invalid"
    assert str(raised.value) == (
        "pitloom_config: must be a non-empty string, got a string ''"
    )
    assert not (project / "out.json").exists()


@pytest.mark.parametrize("kind", ["bogus", "__module__", "Text"])
def test_an_unknown_dataset_type_is_refused(project: Path, kind: str) -> None:
    out = project / "out.json"
    with pytest.raises(ValueError) as raised:
        with loom.run(out):
            loom.add_dataset("a.txt", kind)
    assert code_of(raised.value) == "option-invalid"
    assert str(raised.value).startswith("loom SDK: dataset_type: must be one of ")
    assert not out.exists()


def _types_and_inputs(out: Path) -> tuple[list[list[str]], list[list[str]]]:
    """Each dataset's types, and each ``hasInput``'s inputs, by name."""
    graph = json.loads(out.read_text(encoding="utf-8"))["@graph"]
    names = {e["spdxId"]: e.get("name") for e in graph if "spdxId" in e}
    kinds = [
        e["dataset_datasetType"]
        for e in graph
        if e.get("type") == "dataset_DatasetPackage"
    ]
    inputs = [
        [names[i] for i in e["to"]]
        for e in graph
        if e.get("relationshipType") == "hasInput"
    ]
    return kinds, inputs


def test_what_the_rules_take_is_recorded(project: Path) -> None:
    """The spec's spelling of a type, a ``Path``, tuples for lists."""
    out = project / "out.json"
    (project / "m.bin").write_bytes(b"m")
    with loom.run(out):
        loom.set_model("m", path=Path("m.bin"))
        loom.add_input_dataset("a.txt", "noAssertion")
        loom.add_output_dataset(
            "o.txt", data_preprocessing=("tok",), input_datasets=("a.txt",)
        )
    kinds, inputs = _types_and_inputs(out)
    assert sorted(k.rsplit("/", 1)[-1] for (k,) in kinds) == ["noAssertion", "text"]
    assert inputs == [["a.txt"]]


@pytest.mark.platform
def test_inputs_are_read_at_the_call(project: Path) -> None:
    """A caller's list grown after the call is not what the output read."""
    out = project / "out.json"
    (project / "b.txt").write_bytes(b"b")
    names = ["a.txt"]
    with loom.run(out):
        loom.add_input_dataset("a.txt")
        loom.add_input_dataset("b.txt")
        loom.add_output_dataset("o.txt", input_datasets=names)
        names.append("b.txt")
    assert names == ["a.txt", "b.txt"]
    assert _types_and_inputs(out)[1] == [["a.txt"]]


# pylint: disable-next=too-few-public-methods
class _NoText:
    """An ``os.PathLike`` whose ``__fspath__`` returns no path at all."""

    def __fspath__(self) -> object:
        return 5


@pytest.mark.usefixtures("project")
def test_a_path_like_that_spells_no_path_is_refused() -> None:
    with pytest.raises(TypeError) as raised:
        _sdk.run(_NoText())
    assert code_of(raised.value) == "option-invalid"


def test_a_parameter_with_no_rule_is_a_programming_error() -> None:
    with pytest.raises(InternalError, match="no loom SDK rule for 'nothing'"):
        check_sdk_arguments((), nothing=1)


def test_an_unchecked_dataset_type_is_a_programming_error() -> None:
    with pytest.raises(InternalError, match="not a dataset type: 'bogus'"):
        dataset_kind_of("bogus")
