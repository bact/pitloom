# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""YAML 1.1 corner cases in a dataset card's frontmatter (PyYAML reads
``yes`` as a boolean, ``010`` as 8, ``1:30`` as 90): what the reader keeps
and what it skips with a ``WARNING:``.

See also: tests/extract/dataset/test_card.py (the fields),
tests/extract/dataset/test_reader_fuzz.py (generated input).
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from pitloom.extract.dataset import read_dataset_card


@pytest.mark.parametrize(
    ("yaml", "licence", "version", "warnings"),
    [
        ("license: yes", None, None, 1),  # a boolean, not text
        ("license: on", None, None, 1),
        ("license: 'no'", "no", None, 0),  # quoted: text, as written
        ("license: 010", None, None, 1),
        ("license: !!str 010", "010", None, 0),
        ("license: 2024-01-01", None, None, 1),  # a date
        ("license: null\nversion: ~", None, None, 0),  # nothing stated
        ("license: [mit, yes]", "mit", None, 1),  # the item of no text is lost
        ("version: 010", None, None, 1),
        ("version: yes", None, None, 1),
        ("version: '010'", None, "010", 0),
        ("license: mit\nlicense: apache-2.0", "apache-2.0", None, 0),  # last wins
        ("<<: {license: mit, version: '2'}", "mit", "2", 0),  # merge key
        ("base: &b {license: mit}\n<<: *b", "mit", None, 0),
        ("license: mit\n<<: {license: isc}", "mit", None, 0),  # own key wins
        ("license:\tmit", None, None, 1),  # a tab is not YAML: parse failure
        ("tags:\n\t- a\nlicense: mit", None, None, 1),
        ("a: &a [x, x]\nb: &b [*a, *a, *a]\nlicense: mit", "mit", None, 0),
    ],
    ids=[
        "yes", "on", "quoted-no", "octal-looking", "tagged-str", "date", "null",
        "bad-list-item", "version-octal", "version-yes", "version-quoted",
        "duplicate-key", "merge-key", "merge-alias", "merge-own-wins",
        "tab-value", "tab-indent", "aliases",
    ],
)  # fmt: skip
def test_the_yaml_corner_case(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    yaml: str,
    licence: str | None,
    version: str | None,
    warnings: int,
) -> None:
    (tmp_path / "README.md").write_text(f"---\n{yaml}\n---\n", encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        meta = read_dataset_card(tmp_path)
    if meta is None:  # unparsable frontmatter: no card, one warning
        assert (licence, version, warnings) == (None, None, 1)
    else:
        assert (meta.license, meta.version) == (licence, version)
    assert len(caplog.records) == warnings
