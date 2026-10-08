# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Two model names that share their first 1024 characters keep different
names and ids on every surface: the cut name ends with a digest of the
whole name (:func:`pitloom.core.ai_metadata.cap_model_name`).

See also: :mod:`tests.core.test_ai_metadata` (the cut itself) and
:mod:`tests.extract.ai_model.test_limits` (its warning).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble import enrich_model, generate_model_sbom, generate_project_sbom
from pitloom.core.ai_metadata import MAX_MODEL_NAME_CHARS, cap_model_name
from pitloom.core.models import generate_spdx_id
from tests.extract.ai_model.gguf_builders import STRING, gguf_file, kv, string
from tests.id_registry.surfaces_base import demo_project

_START = "m" * MAX_MODEL_NAME_CHARS


def _gguf(name: str) -> bytes:
    return gguf_file(0, 1, kv(b"general.name", STRING, string(name)))


def _of_type(sbom: str, type_name: str) -> list[dict[str, Any]]:
    graph = json.loads(sbom)["@graph"]
    return [e for e in graph if e["type"] == type_name]


def test_loom_model_gives_two_long_names_two_documents(tmp_path: Path) -> None:
    sboms = []
    for tail in ("a", "b"):
        path = tmp_path / f"{tail}.gguf"
        path.write_bytes(_gguf(_START + tail))
        sboms.append(generate_model_sbom(path))
    documents = [_of_type(s, "SpdxDocument")[0]["spdxId"] for s in sboms]
    (first,), (second,) = (_of_type(s, "ai_AIPackage") for s in sboms)
    assert documents[0] != documents[1]
    assert first["spdxId"] != second["spdxId"]
    assert first["name"] != second["name"]
    assert len(first["name"]) == len(second["name"]) == MAX_MODEL_NAME_CHARS


def test_a_project_and_its_enrichment_fragments_keep_two_long_names_apart(
    tmp_path: Path,
) -> None:
    """Each fragment from ``loom enrich --project-dir`` names its own model's
    package in the project SBOM, not the other one's."""
    root = demo_project(tmp_path)
    for tail in ("a", "b"):
        model_dir = root / "demo" / tail
        model_dir.mkdir()
        (model_dir / "m.gguf").write_bytes(_gguf(_START + tail))
        (model_dir / "README.md").write_text(
            "---\nlicense: mit\n---\n", encoding="utf-8"
        )
    sbom = generate_project_sbom(root, offline=True)
    ids = {p["name"]: p["spdxId"] for p in _of_type(sbom, "ai_AIPackage")}
    assert len(ids) == 2
    for tail in ("a", "b"):
        fragment = enrich_model(root / "demo" / tail / "m.gguf", project_target=root)
        expected = ids[cap_model_name(_START + tail)]
        other = ids[cap_model_name(_START + ("b" if tail == "a" else "a"))]
        assert expected in fragment and other not in fragment


#: Upper bound, in characters, of the part of a package ``spdxId`` minted
#: from a name at the cap (the part after ``#``; the document namespace holds
#: the name once more for ``loom model``). The worst case is a name of 4-byte
#: code points that are not RFC 3987 ``ucschar`` (a private-use or tag
#: character), each percent-encoded to 12 characters: 1012 of them plus the
#: 12-character cut tail, the ``AIPackage-`` prefix and the counter make
#: 12 168. A letter outside ASCII is kept as is: 1036.
_MAX_ID_FRAGMENT_CHARS = 12_200


@pytest.mark.parametrize(
    "char",
    ["\u0e01", " ", "\U000f0000", "\U000e0041"],
    ids=["letter", "space", "private-use", "tag"],
)
def test_an_id_from_a_name_at_the_cap_stays_bounded(char: str) -> None:
    name = cap_model_name(char * (MAX_MODEL_NAME_CHARS + 1))
    doc_uuid = "9e1a7b1c-0000-5000-8000-000000000000"
    spdx_id = generate_spdx_id(f"AIPackage-{name}", doc_name=name, doc_uuid=doc_uuid)
    namespace, _, fragment = spdx_id.partition("#")
    assert len(fragment) <= _MAX_ID_FRAGMENT_CHARS
    assert len(spdx_id) <= 2 * _MAX_ID_FRAGMENT_CHARS + len(doc_uuid) + 64
    assert namespace.endswith(doc_uuid)
