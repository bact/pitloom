# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""One source for the suffixes that could be a model: the scanner's candidate
filter and ``loom generate FILE``'s routing both derive from
:func:`pitloom.core.ai_metadata.model_file_suffixes`.

See also: :mod:`tests.extract.scanner.test_scanner_non_models` (a shared
suffix without a model header) and
:mod:`tests.assemble.test_model_outcome_parity` (the same file on every
surface).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from pitloom.assemble import _MODEL_FILE_EXTENSIONS
from pitloom.core.ai_metadata import (
    SHARED_MODEL_SUFFIXES,
    AiModelFormat,
    model_file_suffixes,
)
from pitloom.core.project import ProjectFile
from pitloom.extract.scanner import _ALLOWED_EXTS, is_model_candidate_name
from pitloom.extract.scanner_project import scan_project_for_ai_models

_MINIMAL = (
    Path(__file__).parent.parent.parent
    / "fixtures"
    / "aimodels"
    / "crfsuite"
    / "minimal.model"
)


def test_both_consumers_derive_from_model_file_suffixes() -> None:
    suffixes = model_file_suffixes()
    assert set(_MODEL_FILE_EXTENSIONS) == suffixes
    assert list(_MODEL_FILE_EXTENSIONS) == sorted(_MODEL_FILE_EXTENSIONS)
    # a zip is an sdist to ``loom generate``, a candidate only to the scanner
    assert _ALLOWED_EXTS == suffixes | {".zip"}
    assert ".zip" not in suffixes
    # every format's own suffixes and the shared ones are in it
    assert suffixes >= SHARED_MODEL_SUFFIXES
    assert suffixes >= {e for f in AiModelFormat for e in f.extensions}
    assert {".bin", ".model", ".crfsuite"} <= suffixes


@pytest.mark.parametrize(
    ("name", "expected"),
    [("m.model", True), ("M.MODEL", True), ("m.crfsuite", True), ("m.models", False)],
)
def test_is_model_candidate_name(name: str, expected: bool) -> None:
    assert is_model_candidate_name(name) is expected


def _scan(root: Path, name: str, data: bytes) -> list[object]:
    (root / name).write_bytes(data)
    return list(
        scan_project_for_ai_models(
            root,
            [ProjectFile(physical_path=name, distribution_path=name)],
            scan_usage=False,
            usage_hint=lambda: False,
        )
    )


def test_a_model_file_without_the_signature_is_silent_in_a_project_scan(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A SentencePiece-shaped ``.model`` (protobuf) logs nothing at INFO or
    above and lists no model."""
    with caplog.at_level(logging.INFO):
        found = _scan(tmp_path, "spiece.model", b"\n\x0f" + bytes(64))
    assert not found
    assert not caplog.records


def test_a_crfsuite_file_named_model_is_listed(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO):
        found = _scan(tmp_path, "tagger.model", _MINIMAL.read_bytes())
    assert len(found) == 1
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
