# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Creator type normalisation: one rule for the constructor, the config
reader and ``build_creator_agents``.

See also:
- :mod:`tests.messages.test_config_guards` for ``creator_type_problem`` on
  unknown and non-string values.
- :mod:`tests.assemble.test_creation_info` for ``build_creator_agents``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3.creation_info import (
    build_creation_info,
    build_creator_agents,
)
from pitloom.core.creation import (
    CreationMetadata,
    Creator,
    creator_type_problem,
    normalised_creator_type,
)
from pitloom.extract.project.pyproject import read_pyproject

pytestmark = pytest.mark.platform

_DOC_NAME = "testproject"
_DOC_UUID = "00000000-0000-0000-0000-000000000000"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "person"),
        ("", "person"),
        (" Organization ", "organization"),
        ("Software-Agent", "software-agent"),
    ],
    ids=["none", "empty", "padded-mixed-case", "mixed-case"],
)
def test_normalised_creator_type(value: str | None, expected: str) -> None:
    """None and empty are ``person`` (the default), the rest is folded."""
    assert normalised_creator_type(value) == expected


@pytest.mark.parametrize("value", [None, ""], ids=["none", "empty"])
def test_creator_without_a_type_is_a_person(value: str | None) -> None:
    """An absent or empty type is the default type, not an unknown one."""
    assert creator_type_problem(value) is None
    assert Creator("A", type=value).type == "person"  # type: ignore[arg-type]


def test_creator_default_type_is_person() -> None:
    assert Creator("A").type == "person"


def test_bytes_is_not_a_string_creator_type() -> None:
    """A bytes value is no string, whatever its text says."""
    assert creator_type_problem(b"person") == "string"
    with pytest.raises(ValueError, match="must be a string"):
        Creator("A", type=b"person")  # type: ignore[arg-type]


def test_agents_build_from_the_normalised_type_of_a_creator_set_late() -> None:
    """A type set after construction is normalised again, not used as written."""
    spdx_ci, _agents, _tools = build_creation_info(
        CreationMetadata(), _DOC_NAME, _DOC_UUID
    )
    creator = Creator("A")
    creator.type = " Organization "
    agents = build_creator_agents(
        CreationMetadata(creators=[creator]), _DOC_NAME, _DOC_UUID, spdx_ci
    )
    assert [type(agent) for agent in agents] == [spdx3.Organization]


@pytest.mark.parametrize(
    ("written", "expected"),
    [("Organization", "organization"), (" person", "person")],
    ids=["mixed-case", "leading-space"],
)
def test_config_creator_type_is_read_as_the_constructor_reads_it(
    tmp_path: Path, written: str, expected: str
) -> None:
    """The config reader accepts what ``Creator`` normalises."""
    path = tmp_path / "pyproject.toml"
    path.write_text(
        '[project]\nname = "p"\nversion = "1.0.0"\n\n'
        f'[[tool.pitloom.creator]]\nname = "Acme"\ntype = "{written}"\n',
        encoding="utf-8",
    )
    _metadata, config = read_pyproject(path)
    assert [(c.name, c.type) for c in config.creators] == [("Acme", expected)]
