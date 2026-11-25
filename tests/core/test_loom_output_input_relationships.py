# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``hasInput`` relationships of the output datasets of a loom run: which
inputs an output names, and what is said of a name no input answers to.

See also:
- :mod:`tests.core.test_loom_active_run_branches` for the guard clauses of
  relationship emission.
- :mod:`tests.messages.test_loom_sdk` for the message itself.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest

from pitloom import loom

from .conftest import _relationships

_UNKNOWN = "which no add_input_dataset of this run declared"


def _has_input(output: Path) -> dict[str, list[str]]:
    """``{output name: [input names]}`` of the ``hasInput`` relationships."""
    graph = json.loads(output.read_text(encoding="utf-8"))["@graph"]
    names = {e["spdxId"]: e.get("name") for e in graph if "spdxId" in e}
    found: dict[str, list[str]] = {}
    for rel in _relationships(graph):
        if rel.get("relationshipType") == "hasInput":
            found[names[rel["from"]]] = [names[i] for i in rel["to"]]
    return found


def test_an_output_naming_no_declared_input_does_not_hide_the_next(
    tmp_path: Path,
) -> None:
    """Each output is resolved on its own: one with nothing to link does not
    end the loop."""
    out = tmp_path / "frag.spdx3.json"
    with loom.run(out) as run:
        run.add_input_dataset("raw.txt")
        run.add_output_dataset("a.txt", input_datasets=["missing.txt"])
        run.add_output_dataset("b.txt", input_datasets=["raw.txt"])
    assert _has_input(out) == {"b.txt": ["raw.txt"]}


def test_an_explicit_empty_list_of_inputs_is_not_all_inputs(tmp_path: Path) -> None:
    """``[]`` means no input; only ``None`` (the default) means every input."""
    out = tmp_path / "frag.spdx3.json"
    with loom.run(out) as run:
        run.add_input_dataset("raw.txt")
        run.add_output_dataset("none.txt", input_datasets=[])
        run.add_output_dataset("all.txt")
    assert _has_input(out) == {"all.txt": ["raw.txt"]}


@pytest.mark.parametrize(
    ("given", "shown"),
    [
        ("gone.txt", "input_datasets='gone.txt',"),
        (None, "input_datasets=None,"),
        (5, "input_datasets='a value of type int',"),
    ],
    ids=["text", "none", "not-a-text"],
)
def test_an_entry_that_is_no_name_is_shown_as_what_it_is(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, given: Any, shown: str
) -> None:
    """An untyped caller may pass any value: a text is shown as given,
    ``None`` as Python shows it, any other value by its type, never by
    ``str()`` of it."""
    out = tmp_path / "frag.spdx3.json"
    with caplog.at_level(logging.WARNING, logger="pitloom.loom"):
        with loom.run(out) as run:
            run.add_input_dataset("raw.txt")
            run.add_output_dataset("out.txt", input_datasets=[given])
    lines = [r.getMessage() for r in caplog.records if _UNKNOWN in r.getMessage()]
    assert len(lines) == 1
    assert f"add_output_dataset('out.txt') names {shown}" in lines[0]
    assert not _has_input(out)
