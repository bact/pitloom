# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The values page: what each ``<name>`` a catalogued line shows stands for.

It is a page of its own, beside the topic pages, so the index stays small as
the catalogue grows (``scripts/generate_message_reference.py``).

See also: tests/messages/test_generated_reference.py (the rest of the
generator).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from pitloom.messages import FIELDS, FRAMES, MESSAGES, TOPIC_TITLES

pytestmark = pytest.mark.platform  # paths: the pages are files beside an index

_SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts" / ("generate_message_reference.py")
)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("generate_message_reference", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


gen = _load()


def _used() -> set[str]:
    named = {n for m in MESSAGES.values() for ln in m.lines for n in ln.fields}
    return named | {n for f in FRAMES for n in f.fields}


@pytest.mark.parametrize("site", gen.SITES, ids=lambda s: s.index.parent.parent.name)
def test_the_values_page_lists_every_name_a_line_uses_once(site: Any) -> None:
    rows = [r for r in gen.render_values_page(site).splitlines() if r.startswith("| `")]
    assert sorted(r.split("`")[1] for r in rows) == sorted(
        FIELDS[n].shown for n in _used()
    )


@pytest.mark.parametrize("site", gen.SITES, ids=lambda s: s.index.parent.parent.name)
def test_the_index_links_the_values_page_and_holds_no_values_table(
    site: Any,
) -> None:
    body = gen.render(site)
    assert f"]({site.values_path.name})" in body
    assert "| Value | What it is |" not in body
    assert site.values_path.name.endswith("-values.md")


def test_a_topic_is_never_named_values() -> None:
    """A topic of that name would write the page the values page owns."""
    assert gen.VALUES_TOPIC not in TOPIC_TITLES


def test_the_values_page_is_an_expected_page_and_never_an_orphan() -> None:
    for site in gen.SITES:
        assert site.values_path in gen.expected_pages(site)
        assert site.values_path not in gen.orphans(site)
