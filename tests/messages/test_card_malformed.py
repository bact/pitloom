# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A model or dataset card that does not read: ``card-malformed`` for a
frontmatter that is not valid YAML, ``file-unreadable`` for a card the
system refuses, ``dir-unlistable`` for a directory that cannot be listed;
absent stays quiet. On the command line (``loom enrich``), the library,
the build hook and a loom dataset.

See also: tests/assemble/test_enrich_readme.py (the reader),
tests/messages/test_file_unreadable.py (the family's helpers).
"""

from __future__ import annotations

import errno
import logging
import os
import sys
import zipfile
from pathlib import Path
from typing import Any

import pytest

from pitloom import __main__, loom
from pitloom.assemble import enrich_model
from pitloom.enrich.readme import (
    DATASET_CARD,
    MODEL_CARD,
    CardKind,
    _parse_frontmatter,
    find_card_file,
    read_card,
)
from pitloom.extract.remote.huggingface_dataset import HUB_DATASET_CARD
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import (
    CARD_KINDS,
    READ_USES,
    trusted_message,
)
from pitloom.messages.files import (
    CARD_MALFORMED,
)
from tests._message_drift import record_problem
from tests._unreadable import deny
from tests.extract.conftest import (
    make_hook,
    staged_sbom,
    write_pyproject_with_pitloom_config,
)

_BAD = "---\nlicense: [unterminated\n---\n"
_NOT_YAML = "frontmatter is not valid YAML; "
_KINDS = [MODEL_CARD, DATASET_CARD, HUB_DATASET_CARD]


def _said(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    found = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert all(record_problem(r) is None for r in found)
    return found


@pytest.mark.parametrize("kind", _KINDS, ids=lambda k: k.label)
def test_each_kind_of_card_names_itself_from_the_tables(kind: CardKind) -> None:
    assert kind.label in CARD_KINDS
    assert kind.use in READ_USES


@pytest.mark.parametrize("kind", _KINDS, ids=lambda k: k.label)
def test_a_frontmatter_that_is_not_yaml_is_card_malformed(
    caplog: pytest.LogCaptureFixture, kind: CardKind
) -> None:
    """Named by the card, the kind, what the parser reported; no list of
    fields after it (the entry says what each kind loses)."""
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        assert _parse_frontmatter(_BAD, kind, shown="d/README.md") is None
    (record,) = _said(caplog)
    text = record.getMessage()
    assert text.startswith(f"FILE=d/README.md: {kind.label} {_NOT_YAML}")
    assert "Field(s)" not in text and "\n" not in text
    assert getattr(record, CODE_ATTR) == "card-malformed"
    assert trusted_message(f"WARNING: {text} [card-malformed]") is CARD_MALFORMED


@pytest.mark.parametrize(
    "text", ["---\n- a\n- b\n---\n", "---\njust text\n---\n", "no frontmatter\n"]
)
def test_a_frontmatter_that_states_no_mapping_is_quiet(
    caplog: pytest.LogCaptureFixture, text: str
) -> None:
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        assert _parse_frontmatter(text, shown="README.md") is None
    assert not caplog.records


def test_the_card_field_takes_only_a_kind_of_its_table() -> None:
    (line,) = CARD_MALFORMED.lines
    values = {"file": "a", "failure": ValueError("x")}
    assert line.render({**values, "card": "dataset card"}).startswith("FILE=a: ")
    with pytest.raises(ValueError, match="is not a card"):
        line.render({**values, "card": "readme"})


def test_a_card_the_system_refuses_is_file_unreadable_without_its_errno(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """What the system reported, never the exception's text (``[Errno 13]
    ...`` and the path again)."""
    card = tmp_path / "README.md"
    card.write_text("---\nlicense: mit\n---\n", encoding="utf-8")
    with (
        deny(card, "open", monkeypatch),
        caplog.at_level(logging.WARNING, logger="pitloom"),
    ):
        assert read_card(card, MODEL_CARD) is None
    (record,) = _said(caplog)
    assert record.getMessage() == (
        f"FILE={card}: could not read for the model card; Permission denied"
    )
    assert getattr(record, CODE_ATTR) == "file-unreadable"


def test_a_card_gone_since_it_was_found_is_quiet(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        assert read_card(tmp_path / "README.md", DATASET_CARD) is None
    assert not caplog.records


def _iterdir_raising(
    monkeypatch: pytest.MonkeyPatch, directory: Path, code: int
) -> None:
    """Listing *directory* raises ``OSError(code)``; any other lists."""
    real = Path.iterdir

    def iterdir(self: Path) -> Any:
        if os.path.abspath(self) == os.path.abspath(directory):
            raise OSError(code, os.strerror(code), str(self))
        return real(self)

    monkeypatch.setattr(Path, "iterdir", iterdir)


@pytest.mark.parametrize("kind", [MODEL_CARD, DATASET_CARD], ids=lambda k: k.label)
def test_a_directory_that_cannot_be_listed_says_so(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    kind: CardKind,
) -> None:
    """Its card is not found, and one line says why."""
    (tmp_path / "README.md").write_text(_BAD, encoding="utf-8")
    _iterdir_raising(monkeypatch, tmp_path, errno.EACCES)
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        assert find_card_file(tmp_path, kind) is None
    (record,) = _said(caplog)
    assert record.getMessage() == (
        f"DIR={tmp_path}: could not list {kind.use}; Permission denied"
    )
    assert getattr(record, CODE_ATTR) == "dir-unlistable"


@pytest.mark.parametrize("code", [errno.ENOENT, errno.ENOTDIR], ids=["gone", "file"])
def test_a_directory_that_is_absent_is_quiet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    code: int,
) -> None:
    _iterdir_raising(monkeypatch, tmp_path, code)
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        assert find_card_file(tmp_path, MODEL_CARD) is None
    assert not caplog.records


def _keras(path: Path) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in (
            ("metadata.json", '{"keras_version": "3.0.0"}'),
            ("config.json", '{"class_name": "Sequential", "config": {"name": "m"}}'),
            ("model.weights.h5", ""),
        ):
            archive.writestr(zipfile.ZipInfo(name), data)
    return path


def _model_with_bad_card(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "README.md").write_text(_BAD, encoding="utf-8")
    return _keras(directory / "m.keras")


def test_loom_enrich_prints_the_code_and_exits_0(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    model = _model_with_bad_card(tmp_path)
    out = tmp_path / "fragment.json"
    monkeypatch.setattr(sys, "argv", ["loom", "enrich", str(model), "-o", str(out)])
    assert __main__.main() == 0
    (line,) = [ln for ln in capsys.readouterr().err.splitlines() if _NOT_YAML in ln]
    card = tmp_path / "README.md"
    assert line.startswith(f"WARNING: FILE={card}: model card {_NOT_YAML}")
    assert line.endswith(" [card-malformed]")


def test_the_library_record_carries_the_code(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    model = _model_with_bad_card(tmp_path)
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        enrich_model(model)
    (record,) = [r for r in _said(caplog) if _NOT_YAML in r.getMessage()]
    assert getattr(record, CODE_ATTR) == "card-malformed"


def test_the_build_hook_record_carries_the_code(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A project that enriches (``enrich = true``) reads the card beside its
    model: the hook says the same line."""
    write_pyproject_with_pitloom_config(
        tmp_path,
        '[tool.hatch.build.targets.wheel]\npackages = ["testpkg"]\n'
        "\n[tool.pitloom]\nenrich = true\n",
    )
    _model_with_bad_card(tmp_path / "testpkg")
    (tmp_path / "testpkg" / "__init__.py").write_text("", encoding="utf-8")
    hook = make_hook(str(tmp_path), {})
    build_data: dict[str, Any] = {}
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        hook.initialize("standard", build_data)
    try:
        assert staged_sbom(build_data) is not None
    finally:
        hook.finalize("standard", build_data, "")
    said = [r for r in _said(caplog) if _NOT_YAML in r.getMessage()]
    assert said and {getattr(r, CODE_ATTR) for r in said} == {"card-malformed"}


def test_a_loom_dataset_card_record_carries_the_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "corpus").mkdir()
    (tmp_path / "corpus" / "README.md").write_text(_BAD, encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        with loom.run(tmp_path / "out.json"):
            loom.add_dataset("corpus")
    (record,) = [r for r in _said(caplog) if _NOT_YAML in r.getMessage()]
    assert record.getMessage().startswith(
        f"FILE={Path('corpus') / 'README.md'}: dataset card {_NOT_YAML}"
    )
    assert getattr(record, CODE_ATTR) == "card-malformed"
