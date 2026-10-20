# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Seeded, generated hostile input for every dataset reader entry point: a
Croissant file, a local dataset card, a Hub dataset card and a local model
card's ``datasets:``. Each either returns a valid result or, for a Croissant
file, raises the documented ``ValueError``; nothing else escapes, and what
is returned holds only text and numbers an SBOM can write.

The same seeds give the same inputs on every run (``random.Random(seed)``).

See also: fuzz/ (the coverage-guided harnesses) and
tests/extract/dataset/test_placeholders.py (the rules, case by case).
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from pitloom.core.ai_metadata import AiModelMetadata
from pitloom.core.canonical_json import MAX_SAFE_INTEGER
from pitloom.core.dataset_metadata import DatasetMetadata
from pitloom.enrich.readme import ReadmeEnricher
from pitloom.extract.dataset import read_croissant, read_dataset_card
from pitloom.extract.dataset.croissant_key import (
    CREATOR_KEYS,
    DATA_TYPE_KEYS,
    DESCRIPTION_KEYS,
    KEYWORDS_KEYS,
    LICENSE_KEYS,
    RECORD_SET_KEYS,
    TOTAL_ITEMS_KEYS,
    URL_KEYS,
    VERSION_KEYS,
)
from pitloom.extract.remote.huggingface_dataset import _load_dataset_card

#: How many inputs each seed makes: small, the whole file runs in seconds.
_PER_SEED = 25
_SEEDS = [1, 2, 3, 4]

_BOM = "\N{ZERO WIDTH NO-BREAK SPACE}"
_STRINGS = [
    "", " ", "unknown", "N/A", "NOASSERTION", "other", "MIT", "mit OR apache-2.0",
    "\ud800", "a\udc00b", "\x00", _BOM, "\N{RIGHT-TO-LEFT OVERRIDE}", "a\nb", "\t",
    "x" * 5000,
    "https://example.org/d", "s3://b/k", "1.10", "yes", "null", "0x1F",
    "{{", "---", "[", "\U0001f600",
]  # fmt: skip
_NUMBERS = [0, -1, 1.5, 2**53, 2**200, 10**4000, float("nan"), float("inf"), True]
_KEYS = [
    *VERSION_KEYS, *URL_KEYS, *LICENSE_KEYS, *CREATOR_KEYS, *DESCRIPTION_KEYS,
    *KEYWORDS_KEYS, *TOTAL_ITEMS_KEYS, *DATA_TYPE_KEYS, *RECORD_SET_KEYS,
    "rai:dataCollection", "rai:dataBiases", "rai:personalSensitiveInformation",
    "rai:dataPreprocessingProtocol", "@context", "@type", "name",
]  # fmt: skip


def _value(rng: random.Random, depth: int = 0) -> Any:
    """A hostile JSON value: scalars, and lists and objects of them."""
    kind = rng.randrange(8 if depth < 3 else 4)
    if kind == 0:
        return None
    if kind == 1:
        return rng.choice(_NUMBERS)
    if kind in (2, 3):
        return rng.choice(_STRINGS)
    if kind in (4, 5):
        return [_value(rng, depth + 1) for _ in range(rng.randrange(4))]
    return {rng.choice(_KEYS): _value(rng, depth + 1) for _ in range(rng.randrange(4))}


def _croissant(rng: random.Random) -> bytes:
    doc: dict[str, Any] = {"name": "ds"}
    for key in rng.sample(_KEYS, rng.randrange(1, 12)):
        doc[key] = _value(rng)
    if rng.random() < 0.15:
        doc["name"] = _value(rng)  # the one field a document must have
    nested = rng.random() < 0.1
    if nested:  # spliced as text: building it would hit the parser's own limit
        doc[rng.choice(RECORD_SET_KEYS)] = "NESTED"
    raw = json.dumps(doc, ensure_ascii=rng.random() < 0.5).encode("utf-8", "replace")
    if nested:
        levels = rng.choice([10, 63, 64, 1500])
        deep = b"[" * levels + b"]" * levels
        raw = raw.replace(b'"NESTED"', deep, 1)
    roll = rng.random()
    if roll < 0.1:
        raw = b"\xef\xbb\xbf" + raw
    elif roll < 0.2:
        raw = raw[: rng.randrange(len(raw) + 1)]
    elif roll < 0.3:
        at = rng.randrange(len(raw) + 1)
        raw = raw[:at] + rng.choice([b"\x00", b"\xff", b"\\ud800"]) + raw[at:]
    return raw


_YAML_VALUES = [
    "", "null", "~", "yes", "No", "on", "OFF", "010", "0o10", "0x1F", "1:30:00",
    "1e400", ".inf", ".nan", "2024-02-30", "2024-01-01", "'unknown'", "N/A",
    "[a, b]", "[]", "{}", "{a: 1}", "[[[[[[[[[[1]]]]]]]]]]", "- x", "!!python/name:os",
    "!!binary |\n  AAAA", "*undefined", "&a x", "'\\ud800'", '"\\ud800"',
    _BOM + "x",
    "\tx", "other", "mit", "https://example.org/l", "'1.10'", "1.10",
    "'" + "x" * 3000 + "'",
]  # fmt: skip
_YAML_KEYS = [
    "license", "license_name", "license_link", "pretty_name", "version", "tags",
    "datasets", "<<", "? complex", "yes", "null", "license",  # a duplicate key
]  # fmt: skip


def _card(rng: random.Random) -> bytes:
    lines = [
        f"{rng.choice(_YAML_KEYS)}: {rng.choice(_YAML_VALUES)}"
        for _ in range(rng.randrange(1, 8))
    ]
    if rng.random() < 0.2:
        lines.append("anchor: &a [x, x, x]\nbomb: &b [*a, *a, *a, *a]\nbomb2: [*b, *b]")
    if rng.random() < 0.2:
        lines.append("base: &base {license: mit}\nmerged:\n  <<: *base")
    if rng.random() < 0.2:
        lines.append("tags:\n\t- tab")
    text = "---\n" + "\n".join(lines) + "\n---\n# Title\n"
    roll = rng.random()
    if roll < 0.15:
        text = text.replace("\n", "\r\n")
    elif roll < 0.3:
        text = text.replace("\n", "\n\x00", 1)
    raw = text.encode("utf-8", "surrogatepass")
    return b"\xef\xbb\xbf" + raw if rng.random() < 0.15 else raw


def _assert_writable(value: object) -> None:
    """Whatever the reader kept is text or a number an SBOM can write."""
    if isinstance(value, str):
        value.encode("utf-8")  # a lone surrogate would raise here
    elif isinstance(value, bool):
        pass
    elif isinstance(value, int):
        assert 0 <= value <= MAX_SAFE_INTEGER
    elif isinstance(value, (list, tuple)):
        for item in value:
            _assert_writable(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            _assert_writable(key)
            _assert_writable(item)
    elif hasattr(value, "__dataclass_fields__"):
        for name in value.__dataclass_fields__:
            _assert_writable(getattr(value, name))
    else:
        assert value is None, f"unexpected {type(value).__name__}"


def _assert_valid(meta: DatasetMetadata) -> None:
    assert isinstance(meta.name, str) and meta.name
    _assert_writable(meta)
    if meta.license is not None:
        assert meta.license.strip() and meta.license.lower() != "unknown"
    for field in ("version", "creator", "license", "download_url"):
        if getattr(meta, field) is None:
            assert field not in meta.provenance  # no claim without a value
    if meta.download_url is not None:
        assert "://" in meta.download_url and not meta.download_url.isspace()


@pytest.mark.parametrize("seed", _SEEDS)
def test_a_croissant_file_is_read_or_refused_as_a_value_error(
    tmp_path: Path, seed: int
) -> None:
    rng = random.Random(seed)
    path = tmp_path / "c.json"
    for _ in range(_PER_SEED):
        path.write_bytes(_croissant(rng))
        try:
            meta = read_croissant(path)
        except ValueError as exc:
            assert "Croissant" in str(exc) and str(path) in str(exc)
        else:
            _assert_valid(meta)


@pytest.mark.parametrize("seed", _SEEDS)
def test_a_dataset_card_is_read_or_skipped_never_raised(
    tmp_path: Path, seed: int
) -> None:
    rng = random.Random(seed)
    for _ in range(_PER_SEED):
        (tmp_path / "README.md").write_bytes(_card(rng))
        meta = read_dataset_card(tmp_path)
        if meta is not None:
            _assert_valid(meta)


@pytest.mark.parametrize("seed", _SEEDS)
def test_a_hub_dataset_card_and_a_model_card_never_raise(
    tmp_path: Path, seed: int
) -> None:
    rng = random.Random(seed)
    card = tmp_path / "README.md"
    for _ in range(_PER_SEED):
        card.write_bytes(_card(rng))
        with patch("huggingface_hub.hf_hub_download", return_value=str(card)):
            text, frontmatter = _load_dataset_card("o/d", None)
        assert text is None or isinstance(text, str)
        assert isinstance(frontmatter, dict)
        model = AiModelMetadata()
        ReadmeEnricher().enrich(model, model_dir=tmp_path)
        for ref in model.datasets:
            _assert_writable(ref.metadata.name)
            assert ref.metadata.name.strip()
