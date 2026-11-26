# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A GGUF dataset conflict is said once per model, dataset and field: the
reader's fold of two entries of one release records the fields it said
(``DatasetReference.said_conflicts``), and the assembler's fold by name
does not say them again, on the reader, the library and the CLI routes.

See also: :mod:`tests.extract.ai_model.test_gguf_datasets` (the reader)
and :mod:`tests.messages.test_dataset_conflict_sites` (the model subject).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
import logging
import struct
from pathlib import Path

import pytest

from pitloom.assemble import generate_model_sbom
from pitloom.assemble.spdx3.document import build_model
from pitloom.core.creation import CreationMetadata
from pitloom.extract.ai_model.gguf import read_gguf
from pitloom.logging_config import CODE_ATTR
from tests._wheel_fixtures import run_cli
from tests.extract.ai_model.gguf_builders import STRING, UINT32, gguf_file, kv, string

pytestmark = pytest.mark.platform

_CREATED = "2026-01-01T00:00:00Z"
_TAIL = "references differ; kept the first"


def _text(key: str, value: str) -> bytes:
    return kv(key.encode(), STRING, string(value))


def _gguf(path: Path, *entries: tuple[str, str]) -> Path:
    """A GGUF file at *path* naming dataset ``d`` once per (version, url)
    of *entries*, in order."""
    pytest.importorskip("gguf")
    pairs = [kv(b"general.dataset.count", UINT32, struct.pack("<I", len(entries)))]
    for index, (version, url) in enumerate(entries):
        pairs += [
            _text(f"general.dataset.{index}.name", "d"),
            _text(f"general.dataset.{index}.version", version),
            _text(f"general.dataset.{index}.repo_url", f"https://x.org/{url}"),
        ]
    path.write_bytes(gguf_file(0, len(pairs), b"".join(pairs)))
    return path


#: d@1 url a, d@1 url b, d@2 url c: the reader folds the first two (a
#: location conflict), the assembler folds d@1 and d@2 (a version and a
#: location conflict).
_THREE = (("1", "a"), ("1", "b"), ("2", "c"))


def _conflicts(lines: list[str]) -> list[str]:
    return [line for line in lines if _TAIL in line]


def _logged(caplog: pytest.LogCaptureFixture) -> list[str]:
    return _conflicts(
        [r.getMessage() for r in caplog.records if getattr(r, CODE_ATTR, None)]
    )


def test_the_reader_records_the_fields_it_said(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING):
        meta = read_gguf(_gguf(tmp_path / "m.gguf", *_THREE))
    assert [ref.said_conflicts for ref in meta.datasets] == [
        frozenset({"download_url"}),
        frozenset(),
    ]
    assert _logged(caplog) == [f"FILE=m.gguf DATASET='d' FIELD=download_url: {_TAIL}"]


def test_read_then_built_says_each_field_once(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING):
        meta = read_gguf(_gguf(tmp_path / "m.gguf", *_THREE))
        graph = json.loads(
            build_model(meta, CreationMetadata(creation_datetime=_CREATED)).to_json()
        )["@graph"]
    (package,) = [e for e in graph if e["type"] == "dataset_DatasetPackage"]
    assert package["software_downloadLocation"] == "https://x.org/a"
    assert _logged(caplog) == [
        f"FILE=m.gguf DATASET='d' FIELD=download_url: {_TAIL}",
        f"FILE=m.gguf DATASET='d' FIELD=version: {_TAIL}",
    ]


def test_a_field_the_reader_never_said_is_still_said_by_the_assembler(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The reader folds no entry (each release once): every conflict of
    the fold by name is the assembler's to say."""
    meta = read_gguf(_gguf(tmp_path / "m.gguf", ("1", "a"), ("2", "c")))
    assert [ref.said_conflicts for ref in meta.datasets] == [frozenset()] * 2
    with caplog.at_level(logging.WARNING):
        build_model(meta, CreationMetadata(creation_datetime=_CREATED))
    assert _logged(caplog) == [
        f"FILE=m.gguf DATASET='d' FIELD=version: {_TAIL}",
        f"FILE=m.gguf DATASET='d' FIELD=download_url: {_TAIL}",
    ]


def test_the_library_route_says_each_field_once(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    model = _gguf(tmp_path / "m.gguf", *_THREE)
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        generate_model_sbom(
            model,
            output_path=tmp_path / "o.json",
            creation_metadata=CreationMetadata(creation_datetime=_CREATED),
        )
    lines = _logged(caplog)
    assert [line.split("FIELD=")[1].split(":")[0] for line in lines] == [
        "download_url",
        "version",
    ]
    # the model as the caller named it, by both folds
    assert {line.split(" DATASET=")[0] for line in lines} == {f"FILE={model}"}


def test_the_command_line_says_each_field_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _gguf(tmp_path / "m.gguf", *_THREE)
    monkeypatch.chdir(tmp_path)
    run = run_cli(
        monkeypatch,
        capsys,
        "model",
        "m.gguf",
        "-o",
        "o.json",
        "--creation-datetime",
        _CREATED,
    )
    assert run.status == 0, run.err
    assert _conflicts(run.err) == [
        f"WARNING: FILE=m.gguf DATASET='d' FIELD=download_url: {_TAIL} "
        "[dataset-conflict]",
        f"WARNING: FILE=m.gguf DATASET='d' FIELD=version: {_TAIL} [dataset-conflict]",
    ]
