# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The loom SDK's own lines, each said in a ``with loom.run(...)`` block and
carrying its code: a model ``path=`` that is no file at exit (by whether a
registry is loaded), a model with no ``path=``, an output dataset naming an
input never declared, ``inspect.stack`` failing (once per process), and
the coded misuses (no model set, a Croissant URL).

See also: :mod:`pitloom.messages._loom_sdk`, :mod:`tests.core.test_loom_model`.
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from pitloom import loom
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import code_of, trusted_message
from tests.registry_helpers import make_registry

pytestmark = pytest.mark.platform

_SECRET = "pw-s3cr3t"


@pytest.fixture(name="project")
def _project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "pitloom._loom_active_run._get_caller_script_path", lambda: None
    )
    return tmp_path


def _coded(caplog: pytest.LogCaptureFixture) -> list[tuple[str, str]]:
    """``(printed line, code)`` of each record at ``INFO`` or above with a code."""
    return [
        (
            f"{r.levelname}: {r.getMessage()} [{getattr(r, CODE_ATTR)}]",
            getattr(r, CODE_ATTR),
        )
        for r in caplog.records
        if r.levelno >= logging.INFO and hasattr(r, CODE_ATTR)
    ]


def _registry(project: Path) -> Path:
    path = project / "reg.json"
    make_registry({}, path=path)
    return path


@pytest.mark.parametrize(
    ("registry", "given", "text", "code"),
    [
        (
            False,
            "gone.pt",
            "WARNING: loom SDK: model m: path= 'gone.pt' is not a file at exit; "
            "not hashed [model-file-missing]",
            "model-file-missing",
        ),
        (
            True,
            "gone.pt",
            "WARNING: ID registry: loom SDK model m: path= 'gone.pt' is not a file at "
            "exit; looked up ungated: not hashed [registry-hash-missing]",
            "registry-hash-missing",
        ),
        (
            True,
            None,
            "WARNING: ID registry: loom SDK model m has no path=; looked up "
            "ungated: not hashed [registry-hash-missing]",
            "registry-hash-missing",
        ),
        (
            False,
            "a\x00b",
            "WARNING: loom SDK: model m: path= 'a\\x00b' is not a file at exit; "
            "not hashed [model-file-missing]",
            "model-file-missing",
        ),
    ],
    ids=["gone-no-registry", "gone-registry", "no-path-registry", "nul-no-registry"],
)
def test_a_model_without_a_file_says_whether_it_was_looked_up(
    project: Path,
    caplog: pytest.LogCaptureFixture,
    registry: bool,
    given: str | None,
    text: str,
    code: str,
) -> None:
    """With no registry no lookup happens, so the line claims none."""
    kwargs = {"id_registry": _registry(project)} if registry else {}
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        with loom.run(project / "out.json", **kwargs):  # type: ignore[arg-type]
            loom.set_model("m", path=given)
    lines = _coded(caplog)
    assert lines[0] == (text, code)
    assert trusted_message(text) is not None
    assert not any("looked up" in line for line, _ in lines) or registry


def test_no_path_and_no_registry_says_nothing(
    project: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        with loom.run(project / "out.json"):
            loom.set_model("m")
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_an_output_naming_an_undeclared_input_is_coded(
    project: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (project / "a.txt").write_text("a", encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        with loom.run(project / "out.json"):
            loom.add_input_dataset("a.txt")
            loom.add_output_dataset(
                "out\nWARNING: x", input_datasets=[f"https://u:{_SECRET}@h/x"]
            )
    ((line, code),) = _coded(caplog)
    assert code == "reference-not-found/dataset"
    assert line.startswith("WARNING: loom SDK: add_output_dataset('out\\nWARNING: x')")
    assert "input_datasets='https://***:***@h/x'" in line and _SECRET not in line
    assert trusted_message(line) is not None


@pytest.mark.parametrize(
    "fragment",
    ["caller info not determined", "caller script path not determined"],
    ids=["info", "script-path"],
)
def test_inspect_stack_failing_warns_once_per_process(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, fragment: str
) -> None:
    """Both the call's caller and the run's script: one coded ``WARNING``
    however many loom calls, ``DEBUG`` after; the fragment is written."""
    secret = OSError(f"stack https://u:{_SECRET}@h/\n[x]")
    with patch("pitloom._loom_caller.inspect.stack", side_effect=secret):
        with caplog.at_level(logging.DEBUG, logger="pitloom.loom"):
            for _ in range(2):
                with loom.run(tmp_path / "out.json"):
                    loom.set_model("m")
                    loom.add_dataset("d")
    said = [r for r in caplog.records if fragment in r.getMessage()]
    assert [r.levelno for r in said][:1] == [logging.WARNING]
    assert all(r.levelno == logging.DEBUG for r in said[1:]) and len(said) > 1
    printed = f"WARNING: {said[0].getMessage()} [{getattr(said[0], CODE_ATTR)}]"
    assert getattr(said[0], CODE_ATTR) == "caller-info-unreadable"
    assert trusted_message(printed) is not None
    assert _SECRET not in printed and "\n" not in printed
    assert (tmp_path / "out.json").exists()


def test_hyperparameters_before_a_model_is_a_coded_runtime_error(
    project: Path,
) -> None:
    with pytest.raises(RuntimeError) as raised:
        with loom.run(project / "out.json") as run:
            run.set_model_hyperparameters({"lr": "0.01"})
    assert code_of(raised.value) == "option-missing"
    assert str(raised.value).startswith("loom SDK: no model set")
    assert not (project / "out.json").exists()
