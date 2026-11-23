# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The GGUF header reader on hostile input: the fuzz seeds
(``fuzz/gguf_seeds.py``) and the fixtures, each through a seeded mutation
loop. Every outcome is a :class:`GgufHeader` or a :class:`FormatError`,
never another exception.

See also: :mod:`pitloom.extract.ai_model.formats.gguf_header` and
``test_gguf_header.py`` (one case per check).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import importlib.util
import random
from pathlib import Path
from types import ModuleType

import pytest

from pitloom.extract.ai_model.formats import FormatError, Limits
from pitloom.extract.ai_model.formats.gguf_header import GgufHeader, read_gguf_header

_ROOT = Path(__file__).parents[4]
_FIXTURES = _ROOT / "tests" / "fixtures" / "aimodels" / "gguf"
#: Small bounds, so a mutation reaches each of them.
_LIMITS = Limits(
    max_gguf_parsed=2000,
    max_gguf_skipped_elements=2000,
    max_gguf_string_bytes=4096,
    max_gguf_total_string_bytes=65536,
)


def _seeds() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "gguf_seeds", _ROOT / "fuzz" / "gguf_seeds.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_SEEDS: dict[str, bytes] = _seeds().SEEDS


def _mutate(data: bytes, rng: random.Random) -> bytes:
    """*data* with one random flip, overwrite, cut, insertion or deletion."""
    buf = bytearray(data)
    at = rng.randrange(len(buf) + 1)
    kind = rng.randrange(5)
    if kind == 0 and at < len(buf):
        buf[at] ^= 1 << rng.randrange(8)
    elif kind == 1 and at < len(buf):
        buf[at] = rng.choice((0, 1, 0x7F, 0x80, 0xFF))
    elif kind == 2:
        del buf[at:]
    elif kind == 3:
        buf[at:at] = bytes(rng.randrange(256) for _ in range(rng.randrange(1, 9)))
    else:
        del buf[at : at + rng.randrange(1, 9)]
    return bytes(buf)


def _outcome(data: bytes) -> None:
    try:
        header = read_gguf_header(data, _LIMITS, {"general.datasets": 10})
    except FormatError:
        return
    assert isinstance(header, GgufHeader)


@pytest.mark.parametrize("name", _SEEDS)
def test_every_mutation_of_a_seed_is_read_or_refused(name: str) -> None:
    rng = random.Random(name)
    data = _SEEDS[name]
    _outcome(data)
    for _ in range(300):
        _outcome(_mutate(data, rng))


@pytest.mark.parametrize(
    "fixture", sorted(_FIXTURES.glob("*.gguf")), ids=lambda p: p.name
)
def test_every_mutation_of_a_fixture_header_is_read_or_refused(fixture: Path) -> None:
    rng = random.Random(fixture.name)
    data = fixture.read_bytes()[:65536]  # the header: pairs come first
    for _ in range(100):
        _outcome(_mutate(data, rng))
