# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A hostile source label must not forge a provenance segment.

``read_croissant(label=...)``, ``read_dataset_card(label=...)`` and
:func:`~pitloom.extract.dataset.licence.dataset_licence` write the label into
every provenance string; a ``|`` in it would otherwise add an ``Evidence:``
or ``Source:`` segment that a merge acts on.

See also: tests/core/test_provenance.py (the helpers),
tests/extract/dataset/test_card.py, tests/extract/dataset/test_croissant.py.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from pitloom.core.provenance import parse_provenance_value
from pitloom.extract.dataset import read_croissant, read_dataset_card
from pitloom.extract.dataset.licence import dataset_licence

FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "croissant"
BENIGN = "lab"
RLO = chr(0x202E)  # right-to-left override

#: label -> the label as the provenance writes it.
HOSTILE = {
    "pipe": (
        "a | Evidence: not_measured | Reason: over-cap",
        "a / Evidence: not_measured / Reason: over-cap",
    ),
    "semicolon": ("a; Field: b", "a; Field: b"),
    "newline": ("a\n| Field: b", "a\n/ Field: b"),
    "bidi": (f"a{RLO}b", "a\\u202eb"),
}

Reader = Callable[[Path, str], dict[str, str]]


def _croissant(_tmp: Path, label: str) -> dict[str, str]:
    return read_croissant(FIXTURES / "full.json", label=label).provenance


def _card(tmp: Path, label: str) -> dict[str, str]:
    directory = tmp / "card"
    directory.mkdir(exist_ok=True)
    (directory / "README.md").write_bytes(
        b"---\nlicense:\n- mit\n- apache-2.0\npretty_name: Corpus\n"
        b"version: '1.0'\ntags:\n- nlp\n---\n"
    )
    meta = read_dataset_card(directory, label=label)
    assert meta is not None
    return meta.provenance


def _licence_list(_tmp: Path, label: str) -> dict[str, str]:
    found = dataset_licence(
        ["mit", "apache-2.0"], source=label, field_prefix="cardData."
    )
    assert found is not None
    return {"license": found.provenance}


def _licence_other(_tmp: Path, label: str) -> dict[str, str]:
    found = dataset_licence("other", source=label, name="Custom", link="u")
    assert found is not None
    return {"license": found.provenance}


READERS = {
    "croissant": _croissant,
    "card": _card,
    "licence-list": _licence_list,
    "licence-other": _licence_other,
}


@pytest.mark.parametrize("hostile", HOSTILE, ids=list(HOSTILE))
@pytest.mark.parametrize("reader", READERS, ids=list(READERS))
def test_hostile_label_keeps_provenance_shape(
    tmp_path: Path, reader: str, hostile: str
) -> None:
    """Every field's provenance parses to the keys of the benign run, and
    equals it with the label written escaped."""
    label, safe = HOSTILE[hostile]
    run = READERS[reader]
    benign = run(tmp_path, BENIGN)
    forged = run(tmp_path, label)
    assert len(benign) >= 1
    assert forged.keys() == benign.keys()
    suffix = "/README.md" if reader == "card" else ""
    for field, value in benign.items():
        # Guard against a vacuous pass: the benign value names the label.
        assert f"Source: {BENIGN}{suffix}" in value
        assert set(parse_provenance_value(forged[field])) == set(
            parse_provenance_value(value)
        )
        assert forged[field] == value.replace(BENIGN, safe, 1)
