# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Each dataset value check, Croissant name check and display-text escape
says its line with its code (``dataset-field-invalid``,
``dataset-name-missing``, ``text-unsafe``), and the Croissant reader's net
is an :class:`~pitloom.core.internal_error.InternalError`. This module
imports only names the base release had, so each test fails there.

See also: :mod:`tests.messages.test_datasets` (the entries) and
:mod:`tests.messages.test_datasets_hostile` (hostile values).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom import loom
from pitloom.assemble.spdx3.ai import finish_display_text
from pitloom.core.ai_metadata import AiModelMetadata
from pitloom.core.dataset_metadata import DatasetMetadata
from pitloom.core.internal_error import InternalError
from pitloom.extract.dataset.croissant import read_croissant
from pitloom.extract.dataset.values import (
    stated_count,
    stated_text,
    stated_texts,
    stated_url,
    stated_version,
)
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import code_of, trusted_message

pytestmark = pytest.mark.platform

_RLO = "\u202e"


def _printed(caplog: pytest.LogCaptureFixture) -> list[str]:
    """Each coded record at ``INFO`` or above, as printed."""
    return [
        f"{r.levelname}: {r.getMessage()} [{getattr(r, CODE_ATTR)}]"
        for r in caplog.records
        if r.levelno >= logging.INFO and hasattr(r, CODE_ATTR)
    ]


def _one_trusted(caplog: pytest.LogCaptureFixture, code: str) -> str:
    """The one coded line, trusted as *code*."""
    (line,) = _printed(caplog)
    found = trusted_message(line)
    assert found is not None and found.code == code, line
    return line


@pytest.mark.parametrize(
    ("call", "text"),
    [
        (
            lambda: stated_text(5, "c.json", "description"),
            "dataset metadata: SOURCE='c.json' FIELD=description: a value of type "
            "int, not text; skipped",
        ),
        (
            lambda: stated_texts([1, 1, 2], "c.json", "keywords"),
            "dataset metadata: SOURCE='c.json' FIELD=keywords: a value of type "
            "int, not text; skipped",
        ),
        (
            lambda: stated_url("not a url", "m.gguf", "general.dataset.0.repo_url"),
            "dataset metadata: SOURCE='m.gguf' FIELD=general.dataset.0.repo_url: "
            "not a URL; skipped",
        ),
        (
            lambda: stated_version(1.1, "d/README.md", numbers=False),
            "dataset metadata: SOURCE='d/README.md' FIELD=version: a value of type "
            "float, not text; quote it to keep it as written; skipped",
        ),
        (
            lambda: stated_version(1.5, "c.json", numbers=True),
            "dataset metadata: SOURCE='c.json' FIELD=version: a value of type "
            "float, not text; skipped",
        ),
        (
            lambda: stated_count(-1, "imdb", "byte_size"),
            "dataset metadata: SOURCE='imdb' FIELD=byte_size: not a whole number "
            "of zero or more; skipped",
        ),
    ],
    ids=["text", "list-item", "url", "unquoted-version", "json-version", "count"],
)
def test_a_value_its_field_cannot_hold_is_coded(
    caplog: pytest.LogCaptureFixture, call: Callable[[], object], text: str
) -> None:
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        assert call() in (None, [])
    line = _one_trusted(caplog, "dataset-field-invalid")
    assert line == f"WARNING: {text} [dataset-field-invalid]"


@pytest.mark.parametrize(
    ("document", "value_type"),
    [('version: !!binary "aGk="', "bytes"), ("version: !!set {a: null}", "set")],
    ids=["binary", "set"],
)
def test_a_yaml_tag_is_not_told_to_quote(
    caplog: pytest.LogCaptureFixture, document: str, value_type: str
) -> None:
    """Quoting keeps a scalar YAML read from unquoted text; a tagged value
    is no such scalar: the plain line, no advice."""
    value = yaml.safe_load(document)["version"]
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        assert stated_version(value, "d/README.md", numbers=False) is None
    line = _one_trusted(caplog, "dataset-field-invalid")
    assert f"a value of type {value_type}, not text; skipped" in line
    assert "quote it" not in line


def test_a_library_byte_size_is_coded(caplog: pytest.LogCaptureFixture) -> None:
    """A library caller's ``DatasetMetadata(byte_size=-1)``, written."""
    # pylint: disable-next=import-outside-toplevel
    from pitloom.assemble.spdx3.dataset import set_dataset_fields

    package = spdx3.dataset_DatasetPackage(name="imdb")
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        set_dataset_fields(package, DatasetMetadata("imdb", byte_size=-1))
    assert package.dataset_datasetSize is None
    assert "SOURCE='imdb' FIELD=byte_size: not a whole number" in _one_trusted(
        caplog, "dataset-field-invalid"
    )


@pytest.mark.parametrize(
    ("document", "text"),
    [
        (
            {"name": 5},
            "no dataset name: the Croissant name is a value of type int, not "
            "text; not read",
        ),
        ({"description": "x"}, "Croissant document has no name; not read"),
        ({"name": "  "}, "Croissant document has no name; not read"),
    ],
    ids=["not-text", "absent", "blank"],
)
def test_a_croissant_with_no_name_is_coded(
    tmp_path: Path, document: dict[str, object], text: str
) -> None:
    path = tmp_path / "c.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError) as caught:
        read_croissant(str(path), label="c.json")
    assert code_of(caught.value) == "dataset-name-missing"
    assert str(caught.value).endswith(text)
    printed = f"ERROR: {caught.value} [dataset-name-missing]"
    assert trusted_message(printed) is not None


def test_the_croissant_net_is_an_internal_error(tmp_path: Path) -> None:
    path = tmp_path / "c.json"
    path.write_text(json.dumps({"name": "d"}), encoding="utf-8")
    with patch(
        "pitloom.extract.dataset.croissant._extract_croissant_rai_fields",
        side_effect=RecursionError("secret text"),
    ):
        with pytest.raises(InternalError) as caught:
            read_croissant(str(path))
    assert isinstance(caught.value, ValueError)
    assert "RecursionError" in str(caught.value)
    assert "secret text" not in str(caught.value)


def test_a_model_s_escaped_text_is_coded(caplog: pytest.LogCaptureFixture) -> None:
    """The properties sorted and once each, a model's own one bare."""
    own = spdx3.ai_AIPackage(name=f"m{_RLO}", description=f"d{_RLO}")
    data = spdx3.dataset_DatasetPackage(name=f"d{_RLO}")
    creator = spdx3.Organization(name=f"o{_RLO}")
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        finish_display_text(
            AiModelMetadata(),
            [("", own), ("dataset", data), ("dataset", data), ("dataset", creator)],
        )
    line = _one_trusted(caplog, "text-unsafe")
    assert line == (
        "WARNING: FORMAT=unknown FILE=unknown: invisible or bidi control "
        "characters written as \\uXXXX in dataset name, description, name "
        "[text-unsafe]"
    )


def test_a_loom_dataset_s_escaped_text_is_coded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Said when a source writes the dataset's metadata (a declared
    licence here); a name alone writes none, and is not escaped."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "pitloom._loom_active_run._get_caller_script_path", lambda: None
    )
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        with loom.run(tmp_path / "out.json"):
            loom.add_dataset(f"evil{_RLO}txt", declared_license="MIT")
    line = _one_trusted(caplog, "text-unsafe")
    assert line == (
        "WARNING: loom SDK: DATASET='evil\\u202etxt': invisible or bidi control "
        "characters written as \\uXXXX in dataset name [text-unsafe]"
    )


def test_a_loom_dataset_names_its_escaped_properties_sorted_once_each(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A name and a Croissant description both holding a bidi control: one
    line names both, in sorted order."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "pitloom._loom_active_run._get_caller_script_path", lambda: None
    )
    card = tmp_path / "c.json"
    card.write_text(
        json.dumps({"name": "d", "description": f"bad{_RLO}text", "license": "MIT"}),
        encoding="utf-8",
    )
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        with loom.run(tmp_path / "out.json"):
            loom.add_dataset(f"evil{_RLO}txt", croissant=card)
    line = _one_trusted(caplog, "text-unsafe")
    assert line == (
        "WARNING: loom SDK: DATASET='evil\\u202etxt': invisible or bidi control "
        "characters written as \\uXXXX in dataset description, dataset name "
        "[text-unsafe]"
    )
