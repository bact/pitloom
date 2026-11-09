# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The one resolver of a path, a folder, or a folder and a named file to an
SBOM target (:mod:`pitloom.extract.model_target`), for every model format
alike: a named file by its content, a folder's one model, several or none
refused, Git LFS pointers, project vs model mode, the candidate cap, the
silent classifier and the Git URL reader gate.

See also: tests/_model_fixtures.py (one fixture per format) and
tests/core/test_project_markers.py (what makes a project).
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

import pytest

from pitloom.assemble import generate_model_sbom
from pitloom.core.ai_metadata import AiModelFormat
from pitloom.core.creation import CreationMetadata
from pitloom.core.internal_error import InternalError
from pitloom.core.lfs_pointer import reading_remote_clone
from pitloom.core.quote_source import quote_source
from pitloom.extract import model_target
from pitloom.extract.ai_model import (
    detect_ai_model_format_from_header,
    read_ai_model_header,
)
from pitloom.extract.model_target import (
    AUTO,
    MODEL,
    PROJECT,
    ModelFile,
    is_model_file_target,
    model_files_in,
    named_model_file,
    read_model_file,
    require_model_file,
    resolve_sbom_target,
)
from pitloom.extract.scanner_wheel import WHEEL_GATED_FORMATS
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import (
    LFS_CLONE_ERROR_LINE,
    LFS_PULL_ERROR_LINE,
    Cap,
    code_of,
    over_cap_of,
)
from tests._lfs import lfs_pointer_bytes
from tests._model_fixtures import FORMAT_FIXTURES, FORMATS, NEEDS_SUFFIX, fixture_path
from tests._symlink import CAN_SYMLINK

_PINNED = CreationMetadata(creation_datetime="2026-01-01T00:00:00Z")
_PYPROJECT = b'[project]\nname = "demo"\nversion = "1.0"\n'


def _copy(fmt: AiModelFormat, folder: Path, name: str | None = None) -> Path:
    """*fmt*'s fixture copied into *folder* (made if need be) as *name*."""
    folder.mkdir(parents=True, exist_ok=True)
    source = fixture_path(fmt)
    target = folder / (source.name if name is None else name)
    shutil.copyfile(source, target)
    return target


def _codes(caplog: pytest.LogCaptureFixture, level: int) -> list[str | None]:
    return [getattr(r, CODE_ATTR, None) for r in caplog.records if r.levelno == level]


def test_every_format_has_a_fixture_that_sniffs_as_it() -> None:
    """A new format fails here until it has a fixture; the formats a copy
    named ``x.dat`` loses are exactly :data:`NEEDS_SUFFIX`."""
    assert set(FORMAT_FIXTURES) == set(AiModelFormat) - {AiModelFormat.UNKNOWN}
    by_content = set()
    for fmt in FORMATS:
        header = read_ai_model_header(fixture_path(fmt))
        assert detect_ai_model_format_from_header(header, fixture_path(fmt).name) == fmt
        if detect_ai_model_format_from_header(header, "x.dat") == fmt:
            by_content.add(fmt)
    assert set(FORMATS) - by_content == NEEDS_SUFFIX


@pytest.mark.parametrize("fmt", FORMATS, ids=str)
def test_a_named_file_is_a_model_by_its_content(
    fmt: AiModelFormat, tmp_path: Path
) -> None:
    path = _copy(fmt, tmp_path)
    assert named_model_file(path, "m") == ModelFile(path, "m", fmt)
    renamed = _copy(fmt, tmp_path, "x.dat")
    found = named_model_file(renamed, "x.dat")
    if fmt in NEEDS_SUFFIX:
        assert found is None
    else:
        assert found == ModelFile(renamed, "x.dat", fmt)


@pytest.mark.parametrize("fmt", FORMATS, ids=str)
def test_a_folder_s_one_model_is_the_target(
    fmt: AiModelFormat, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = _copy(fmt, tmp_path)
    (tmp_path / "README.md").write_bytes(b"# A model\n")
    assert model_files_in(tmp_path, "sub") == [ModelFile(path, f"sub/{path.name}", fmt)]
    with caplog.at_level(logging.INFO, logger="pitloom"):
        target = resolve_sbom_target(tmp_path, subject="here")
    assert (target.kind, target.folder) == (MODEL, tmp_path)
    assert target.model == ModelFile(path, path.name, fmt)
    (record,) = caplog.records
    assert record.getMessage() == (
        f"FILE={path.name}: no Python project; reading this AI model file"
    )
    assert getattr(record, CODE_ATTR) == "target-ambiguous"


@pytest.mark.parametrize(
    ("mode", "said"),
    [
        (AUTO, "no Python project; reading this AI model file"),
        (MODEL, "the one AI model file; reading it"),
    ],
    ids=["auto", "model"],
)
def test_the_choice_of_a_folder_s_one_model_is_said_by_mode(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, mode: str, said: str
) -> None:
    """One ``INFO:`` (``target-ambiguous``) naming the file as the messages
    name it, whichever SBOM was asked for."""
    path = _copy(AiModelFormat.SAFETENSORS, tmp_path)
    with caplog.at_level(logging.INFO, logger="pitloom"):
        resolve_sbom_target(tmp_path, subject="d", mode=mode, shown_prefix="s")
    assert [r.getMessage() for r in caplog.records] == [f"FILE=s/{path.name}: {said}"]
    assert _codes(caplog, logging.INFO) == ["target-ambiguous"]


def _ambiguous(
    folder: Path,
    names: list[str],
    fmt: AiModelFormat,
    caplog: pytest.LogCaptureFixture,
) -> list[str]:
    """The lines of resolving *folder* with *names* copies of *fmt*'s
    fixture made in that order, then the error's code and text."""
    for name in names:
        _copy(fmt, folder, name)
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="pitloom"):
        with pytest.raises(ValueError) as caught:
            resolve_sbom_target(folder, subject="dir", mode=MODEL)
    assert _codes(caplog, logging.INFO) == ["model-ambiguous"] * len(names)
    return [r.getMessage() for r in caplog.records] + [
        f"{code_of(caught.value)}: {caught.value}"
    ]


@pytest.mark.parametrize("fmt", FORMATS, ids=str)
def test_several_models_are_refused_naming_each_in_order(
    fmt: AiModelFormat, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Plain ``str`` order (``Z`` before ``a``), whatever order the files
    were made in; no two names differ only in case."""
    suffix = fixture_path(fmt).suffix
    names = [f"b{suffix}", f"Z{suffix}", f"a{suffix}"]
    lines = _ambiguous(tmp_path / "one", names, fmt, caplog)
    assert _ambiguous(tmp_path / "two", names[::-1], fmt, caplog) == lines
    assert lines == [
        f"FILE=Z{suffix}: one of several AI model files",
        f"FILE=a{suffix}: one of several AI model files",
        f"FILE=b{suffix}: one of several AI model files",
        "model-ambiguous: 'dir': several AI model files (3 files); name one file",
    ]


#: A pointer's suffix: each format's, a shared one and one a scan never looks at.
_SUFFIXES = sorted({fixture_path(fmt).suffix for fmt in FORMATS} | {".bin"})


@pytest.mark.parametrize("suffix", [*_SUFFIXES, ".dat"])
@pytest.mark.parametrize("remote", [False, True], ids=["checkout", "clone"])
def test_a_named_lfs_pointer_is_refused_for_every_suffix(
    suffix: str, remote: bool, tmp_path: Path
) -> None:
    path = tmp_path / f"m{suffix}"
    path.write_bytes(lfs_pointer_bytes(b"model"))
    with pytest.raises(ValueError) as caught:
        if remote:
            with reading_remote_clone():
                named_model_file(path, path.name)
        else:
            named_model_file(path, path.name)
    assert code_of(caught.value) == "lfs-pointer"
    line = LFS_CLONE_ERROR_LINE if remote else LFS_PULL_ERROR_LINE
    advice = line.template.rpartition("; ")[2]
    assert str(caught.value).startswith(f"'{path.name}': header is a Git LFS ")
    assert str(caught.value).endswith(f"; {advice}")


@pytest.mark.parametrize("suffix", _SUFFIXES)
def test_a_folder_of_pointers_warns_once_then_refuses_the_first(
    suffix: str, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    for stem in ("b", "a"):
        (tmp_path / f"{stem}{suffix}").write_bytes(lfs_pointer_bytes(stem.encode()))
    with pytest.raises(ValueError) as caught:
        model_files_in(tmp_path)
    assert code_of(caught.value) == "lfs-pointer"
    assert f"'a{suffix}'" in str(caught.value)
    assert _codes(caplog, logging.WARNING) == ["lfs-pointer"]
    assert caplog.records[-1].getMessage().startswith(f"FILE=a{suffix}: ")


def test_a_pointer_beside_a_model_is_warned_of_and_the_model_kept(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = _copy(AiModelFormat.SAFETENSORS, tmp_path)
    (tmp_path / "other.gguf").write_bytes(lfs_pointer_bytes())
    found = model_files_in(tmp_path)
    assert [m.path for m in found] == [path]
    assert _codes(caplog, logging.WARNING) == ["lfs-pointer"]


def test_a_file_whose_header_contradicts_its_suffix_is_said_and_skipped(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / "fake.gguf").write_bytes(b"not a model")
    path = _copy(AiModelFormat.SAFETENSORS, tmp_path)
    assert [m.path for m in model_files_in(tmp_path)] == [path]
    assert _codes(caplog, logging.WARNING) == ["model-wrong-format"]
    with pytest.raises(ValueError) as caught:
        named_model_file(tmp_path / "fake.gguf", "fake.gguf")
    assert code_of(caught.value) == "model-wrong-format"


@pytest.mark.parametrize(
    ("name", "content", "code"),
    [
        ("e.gguf", b"", "model-wrong-format"),
        ("x.bin", b"hello", "model-wrong-format"),
        ("gone.onnx", None, "input-not-found"),
        ("x.dat", b"", None),
        ("data.zip", b"PK\x05\x06" + bytes(18), None),
        ("gone.md", None, None),
    ],
    ids=["empty-gguf", "bin", "gone-onnx", "dat", "zip", "gone-md"],
)
def test_a_named_file_is_refused_by_its_model_suffix(
    tmp_path: Path, name: str, content: bytes | None, code: str | None
) -> None:
    """A name a model file has (:func:`has_model_suffix`) and no model is
    refused, as ``generate("e.gguf")`` refuses it; any other name is no
    model (``None``), gone or not."""
    if content is not None:
        (tmp_path / name).write_bytes(content)
    if code is None:
        assert named_model_file(tmp_path / name, name) is None
        return
    with pytest.raises((ValueError, FileNotFoundError)) as caught:
        named_model_file(tmp_path / name, name)
    assert code_of(caught.value) == code


@pytest.mark.parametrize(
    ("mode", "named", "kind"),
    [
        (AUTO, "", PROJECT),
        (PROJECT, "", PROJECT),
        (MODEL, "", MODEL),
        (AUTO, "m.safetensors", MODEL),  # a named model wins over the project
        (PROJECT, "m.safetensors", PROJECT),
        (AUTO, "pyproject.toml", PROJECT),  # plainly not a model: the folder
    ],
    ids=["auto", "project", "model", "named-auto", "named-project", "named-other"],
)
def test_project_or_model_by_mode(
    mode: str, named: str, kind: str, tmp_path: Path
) -> None:
    (tmp_path / "pyproject.toml").write_bytes(_PYPROJECT)
    path = _copy(AiModelFormat.SAFETENSORS, tmp_path, "m.safetensors")
    target = resolve_sbom_target(tmp_path, subject="d", file=named, mode=mode)
    assert target.kind == kind
    expected = ModelFile(path, path.name, AiModelFormat.SAFETENSORS)
    assert target.model == (expected if kind == MODEL else None)


def test_a_named_file_that_is_no_model_reads_the_folder_under_auto_only(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / "README.md").write_bytes(b"# hi\n")
    path = _copy(AiModelFormat.GGUF, tmp_path)
    with caplog.at_level(logging.INFO, logger="pitloom"):
        target = resolve_sbom_target(
            tmp_path, subject="d", file="README.md", shown_prefix="s"
        )
    assert target.model == ModelFile(path, f"s/{path.name}", AiModelFormat.GGUF)
    messages = [r.getMessage() for r in caplog.records]
    assert messages[0] == "FILE=s/README.md: not an AI model file; reading its folder"
    assert _codes(caplog, logging.INFO) == ["target-ambiguous"] * 2
    with pytest.raises(ValueError) as caught:
        resolve_sbom_target(tmp_path, subject="d", file="README.md", mode=MODEL)
    assert code_of(caught.value) == "model-wrong-format"
    with pytest.raises(FileNotFoundError) as missing:
        resolve_sbom_target(tmp_path, subject="d", file="gone.gguf", shown_prefix="s")
    assert code_of(missing.value) == "input-not-found"
    assert str(missing.value) == "Model file not found: 's/gone.gguf'"


@pytest.mark.parametrize(
    ("mode", "code", "text"),
    [
        (
            AUTO,
            "project-or-model-not-found",
            "'d': no Python project (pyproject.toml, setup.cfg or setup.py) and "
            "no AI model file of a supported format; name a project folder or a "
            "model file",
        ),
        (
            MODEL,
            "model-wrong-format",
            "'d': not an AI model file of a supported format",
        ),
    ],
    ids=["auto", "model"],
)
def test_a_folder_with_neither_is_refused(
    mode: str, code: str, text: str, tmp_path: Path
) -> None:
    (tmp_path / "README.md").write_bytes(b"# hi\n")
    (tmp_path / "sub").mkdir()
    _copy(AiModelFormat.GGUF, tmp_path / "sub")  # a subfolder is not searched
    with pytest.raises(ValueError) as caught:
        resolve_sbom_target(tmp_path, subject="d", mode=mode)
    assert (code_of(caught.value), str(caught.value)) == (code, text)


def test_a_folder_over_the_candidate_cap_is_refused_unread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(model_target, "MAX_FOLDER_CANDIDATES", 2)
    for name in ("a.bin", "b.bin"):
        (tmp_path / name).write_bytes(b"x")
    (tmp_path / "c.txt").write_bytes(b"x")  # not a candidate: not counted
    assert not model_files_in(tmp_path)
    (tmp_path / "c.bin").write_bytes(b"x")
    caplog.clear()
    with pytest.raises(ValueError) as caught:
        model_files_in(tmp_path, subject="d")
    assert code_of(caught.value) == "model-ambiguous/over-cap"
    assert str(caught.value) == (
        "'d': more than 2 files that could be AI models, none read; name one file"
    )
    (record,) = caplog.records
    assert record.getMessage() == (
        "DIR=d: larger than the 2-entry model-candidate cap; no file read"
    )
    assert getattr(record, CODE_ATTR) == "over-cap"
    assert over_cap_of(record) == (
        Cap(2, "entry", "model-candidate", "DIR"),
        "no file read",
    )


def test_an_unknown_mode_is_a_programming_error(tmp_path: Path) -> None:
    with pytest.raises(InternalError, match="unknown SBOM target mode"):
        resolve_sbom_target(tmp_path, subject="d", mode="dataset")


def test_a_missing_model_file_is_said_by_the_catalogue(tmp_path: Path) -> None:
    """Read on its own: ``input-not-found``, a FileNotFoundError naming the
    file as given, quoted."""
    gone = tmp_path / "gone.gguf"
    with pytest.raises(FileNotFoundError) as caught:
        read_model_file(gone)
    assert code_of(caught.value) == "input-not-found"
    assert str(caught.value) == f"Model file not found: {quote_source(gone)}"
    with pytest.raises(FileNotFoundError) as shown:
        read_model_file(gone, shown="repo/gone.gguf")
    assert str(shown.value) == "Model file not found: 'repo/gone.gguf'"


def test_a_path_that_cannot_be_looked_at_is_no_missing_file(tmp_path: Path) -> None:
    """A name too long to look up is there or not: its own error stands,
    not ``input-not-found``."""
    if os.name == "nt":
        pytest.skip("Windows reports a long name differently")
    with pytest.raises(OSError) as caught:
        require_model_file(tmp_path / ("a" * 300), "long")
    assert not isinstance(caught.value, FileNotFoundError)
    assert code_of(caught.value) is None


@pytest.mark.skipif(not CAN_SYMLINK, reason="needs a file symlink")
def test_a_link_in_a_git_url_s_folder_is_not_followed(tmp_path: Path) -> None:
    outside = _copy(AiModelFormat.SAFETENSORS, tmp_path / "outside")
    folder = tmp_path / "clone"
    folder.mkdir()
    (folder / "linked.safetensors").symlink_to(outside)
    assert [m.shown for m in model_files_in(folder)] == ["linked.safetensors"]
    with reading_remote_clone():
        assert not model_files_in(folder)


def test_the_cap_names_the_folder_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(model_target, "MAX_FOLDER_CANDIDATES", 0)
    (tmp_path / "a.bin").write_bytes(b"x")
    with pytest.raises(ValueError) as caught:
        model_files_in(tmp_path)
    where = quote_source(str(tmp_path))
    assert str(caught.value) == (
        f"{where}: more than 0 files that could be AI models, none read; name one file"
    )
    assert caplog.messages == [
        f"DIR={tmp_path}: larger than the 0-entry model-candidate cap; no file read"
    ]


def test_the_classifier_falls_back_to_the_suffix_on_a_read_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _denied(path: Path) -> bytes:
        raise PermissionError(13, "Permission denied", str(path))

    monkeypatch.setattr(model_target, "read_ai_model_header", _denied)
    renamed = _copy(AiModelFormat.GGUF, tmp_path, "x.dat")
    assert not is_model_file_target(renamed)
    assert is_model_file_target(_copy(AiModelFormat.GGUF, tmp_path))


@pytest.mark.parametrize("fmt", FORMATS, ids=str)
def test_the_classifier_is_silent_and_reads_content(
    fmt: AiModelFormat, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    assert is_model_file_target(fixture_path(fmt))
    renamed = _copy(fmt, tmp_path, "x.dat")
    assert is_model_file_target(renamed) is (fmt not in NEEDS_SUFFIX)
    assert is_model_file_target(str(renamed)) is (fmt not in NEEDS_SUFFIX)
    assert not caplog.records


@pytest.mark.parametrize(
    "name",
    ["p-1.0.tar.gz", "p-1.0.zip", "p-1.0-py3-none-any.whl", "README.md", "dir"],
)
def test_the_classifier_refuses_archives_and_others(
    name: str, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    path = tmp_path / name
    if name == "dir":
        path.mkdir()
    elif name == "README.md":
        path.write_bytes(b"# not a model\n")
    else:  # GGUF magic does not make an archive a model
        path.write_bytes(fixture_path(AiModelFormat.GGUF).read_bytes()[:64])
    assert not is_model_file_target(path)
    assert not is_model_file_target(tmp_path / "gone.gguf")
    assert not caplog.records


@pytest.mark.parametrize("fmt", FORMATS, ids=str)
def test_a_model_from_a_git_url_is_read_only_in_safe_formats(
    fmt: AiModelFormat, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Decision D1: in a temporary clone a gated format keeps a format-only
    entry, said in one ``reader-unsafe/remote`` line; the others are read
    as anywhere."""
    path = _copy(fmt, tmp_path)
    with caplog.at_level(logging.INFO, logger="pitloom"), reading_remote_clone():
        meta = read_model_file(path, shown="sub/m")
    gated = fmt in WHEEL_GATED_FORMATS
    assert meta.format_info.model_format == fmt
    assert meta.format_info.physical_path == "sub/m"
    infos = [r for r in caplog.records if getattr(r, CODE_ATTR, None)]
    unsafe = [r for r in infos if getattr(r, CODE_ATTR) == "reader-unsafe/remote"]
    assert len(unsafe) == gated
    if gated:
        assert f"downloaded file: {fmt}; clone " in unsafe[0].getMessage()
        assert not meta.provenance


@pytest.mark.parametrize("fmt", FORMATS, ids=str)
def test_a_folder_gives_the_sbom_of_its_model_file(
    fmt: AiModelFormat, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = _copy(fmt, tmp_path / "models")
    (tmp_path / "models" / "README.md").write_bytes(b"# hi\n")
    caplog.set_level(logging.INFO)
    by_folder = generate_model_sbom(path.parent, creation_metadata=_PINNED)
    by_file = generate_model_sbom(path, creation_metadata=_PINNED)
    assert by_folder == by_file
    assert path.name in by_file and str(tmp_path) not in by_file
