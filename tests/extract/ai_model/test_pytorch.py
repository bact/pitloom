# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the classic PyTorch metadata extractor (.pt, .pth).

Covers mocked and integration tests.
"""

# pylint: disable=missing-function-docstring
# pylint: disable=redefined-outer-name
# pylint: disable=use-implicit-booleaness-not-comparison

from __future__ import annotations

import io as _io
import logging
import zipfile as _zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from pitloom.core.ai_metadata import AiModelFormat
from pitloom.extract.ai_model.pytorch import (
    _dotted_name,
    _fickling_get_top_class,
    _read_pytorch_zip,
    read_pytorch,
)

# ---------------------------------------------------------------------------
# Classic PyTorch extractor (mocked / stdlib ZIP)
# ---------------------------------------------------------------------------

_PYTORCH_DIR = Path(__file__).parent.parent.parent / "fixtures" / "aimodels" / "pytorch"


def _make_pytorch_zip(
    files: dict[str, bytes] | None = None,
) -> bytes:
    """Build a minimal in-memory ZIP archive for PyTorch model testing."""
    buf = _io.BytesIO()
    with _zipfile.ZipFile(buf, "w") as zf:
        for name, data in (files or {}).items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_fickling_missing_fallback_holds_with_fickle_already_imported() -> None:
    """Blocking ``fickling`` must also block the already-imported
    ``fickling.fickle`` submodule the reader imports -- otherwise the import
    reuses the loaded module and the fallback runs only when no earlier
    test in the same worker imported it (order-dependent coverage)."""
    pytest.importorskip("fickling.fickle")
    # Protocol-2 pickle of collections.OrderedDict(): real fickling names it.
    data = b"\x80\x02ccollections\nOrderedDict\nq\x00)Rq\x01."
    assert _fickling_get_top_class(_io.BytesIO(data)) == "OrderedDict"
    with patch.dict("sys.modules", {"fickling": None, "fickling.fickle": None}):
        assert _fickling_get_top_class(_io.BytesIO(data)) is None


def test_read_pytorch_format(tmp_path: Path) -> None:
    model_file = tmp_path / "model.pt"
    model_file.write_bytes(
        _make_pytorch_zip({"archive/data.pkl": b"\x80\x04\x95\x00\x00\x00\x00."})
    )
    with patch.dict("sys.modules", {"fickling": None, "fickling.fickle": None}):
        meta = read_pytorch(model_file)
    assert meta.format_info.model_format == AiModelFormat.PYTORCH


def test_read_pytorch_archive_contents_in_properties(tmp_path: Path) -> None:
    model_file = tmp_path / "model.pt"
    model_file.write_bytes(
        _make_pytorch_zip(
            {
                "archive/data.pkl": b"\x80\x02.",
                "archive/version": b"1",
            }
        )
    )
    with patch.dict("sys.modules", {"fickling": None, "fickling.fickle": None}):
        meta = read_pytorch(model_file)
    assert "archive_contents" in meta.properties
    assert "archive/data.pkl" in meta.properties["archive_contents"]


def test_read_pytorch_pth_format(tmp_path: Path) -> None:
    model_file = tmp_path / "model.pth"
    model_file.write_bytes(_make_pytorch_zip({"archive/data.pkl": b"\x80\x02."}))
    with patch.dict("sys.modules", {"fickling": None, "fickling.fickle": None}):
        meta = read_pytorch(model_file)
    assert meta.format_info.model_format == AiModelFormat.PYTORCH


def test_read_pytorch_raw_pickle_format_detail(tmp_path: Path) -> None:
    # A file that is NOT a ZIP is treated as raw pickle.
    model_file = tmp_path / "model.pt"
    model_file.write_bytes(b"\x80\x02}q\x00.")  # minimal raw pickle (empty dict)
    with patch.dict("sys.modules", {"fickling": None, "fickling.fickle": None}):
        meta = read_pytorch(model_file)
    assert meta.format_info.model_format == AiModelFormat.PYTORCH
    assert meta.properties.get("format_detail") == "raw pickle"


def test_read_pytorch_no_fickling_type_of_model_is_none(tmp_path: Path) -> None:
    model_file = tmp_path / "model.pt"
    model_file.write_bytes(_make_pytorch_zip({"archive/data.pkl": b"\x80\x02."}))
    with patch.dict("sys.modules", {"fickling": None, "fickling.fickle": None}):
        meta = read_pytorch(model_file)
    assert meta.type_of_model is None


def test_read_pytorch_no_name_version(tmp_path: Path) -> None:
    model_file = tmp_path / "model.pt"
    model_file.write_bytes(_make_pytorch_zip({"archive/data.pkl": b"\x80\x02."}))
    with patch.dict("sys.modules", {"fickling": None, "fickling.fickle": None}):
        meta = read_pytorch(model_file)
    assert meta.name is None
    assert meta.version is None


# ---------------------------------------------------------------------------
# Malformed input -- exceptions are caught, logged at debug level, and
# degrade gracefully.
# ---------------------------------------------------------------------------


def test_fickling_get_top_class_malformed_pickle_logs_and_returns_none(
    caplog: pytest.LogCaptureFixture,
) -> None:
    pytest.importorskip("fickling")

    # b"\x80\x99" starts a pickle stream (protocol opcode) but is truncated
    # before a STOP opcode, so fickling's AST parser raises.
    with caplog.at_level(logging.DEBUG, logger="pitloom.extract.ai_model.pytorch"):
        result = _fickling_get_top_class(_io.BytesIO(b"\x80\x99"))

    assert result is None
    assert any(
        "fickling failed to parse pickle bytes" in r.message for r in caplog.records
    )


def test_read_pytorch_zip_inspect_failure_logs_and_continues(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A ZIP entry that exists in the file list but fails to read (e.g. a
    corrupt/encrypted archive member) is caught, logged, and the function
    still returns its normal (type_of_model=None) result rather than
    raising."""
    mock_zf = MagicMock()
    mock_zf.namelist.return_value = ["archive/data.pkl"]
    mock_zf.open.side_effect = RuntimeError("bad CRC-32")

    with caplog.at_level(logging.DEBUG, logger="pitloom.extract.ai_model.pytorch"):
        type_of_model, properties, _, provenance = _read_pytorch_zip(
            mock_zf, "Source: model.pt"
        )

    assert type_of_model is None
    assert "type_of_model" not in provenance
    assert "archive_contents" in properties
    assert any("archive/data.pkl" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Integration tests -- classic PyTorch fixtures (pytorch/*.pt, *.pth)
# Require: fixture files present (fickling optional for class name extraction)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def pytorch_fixture() -> Any:
    pt_files = list(_PYTORCH_DIR.glob("*.pt")) + list(_PYTORCH_DIR.glob("*.pth"))
    if not pt_files:
        pytest.skip("No .pt/.pth fixture files found in tests/fixtures/pytorch/")
    return read_pytorch(pt_files[0])


def test_pytorch_fixture_format(pytorch_fixture: Any) -> None:
    assert pytorch_fixture.format_info.model_format == AiModelFormat.PYTORCH


def test_read_pytorch_zip_large_file_list() -> None:
    """_read_pytorch_zip truncates and summarises archive contents if > 20 entries."""
    mock_zf = MagicMock()
    mock_zf.namelist.return_value = [f"file_{i}.bin" for i in range(25)]

    _, properties, raw_metadata, provenance = _read_pytorch_zip(
        mock_zf, "Source: model.pt"
    )
    assert "... (25 total)" in properties["archive_contents"]
    raw = raw_metadata["raw_metadata"]
    assert raw["archive_contents"] == [f"file_{i}.bin" for i in range(20)]
    assert properties["archive_member_count"] == "25"
    assert raw["archive_member_count"] == "25"
    assert raw_metadata["raw_metadata_types"] == {"archive_member_count": "integer"}
    assert "properties.archive_member_count" in provenance


def test_read_pytorch_is_zipfile_oserror(tmp_path: Path) -> None:
    """read_pytorch treats files raising OSError on zip check as raw pickle."""
    fake_pt = tmp_path / "corrupt.pt"
    fake_pt.write_bytes(b"\x80\x04\x95\x00\x00\x00\x00\x00\x00\x00\x00.")

    with patch("zipfile.is_zipfile", side_effect=OSError("disk read error")):
        meta = read_pytorch(fake_pt)
        assert meta.properties.get("format_detail") == "raw pickle"


def test_read_pytorch_corrupt_zip_raises_value_error(tmp_path: Path) -> None:
    """A file that passes the ``zipfile.is_zipfile()`` signature check but
    fails to actually open (truncated/corrupt central directory) must
    raise ValueError, not propagate a bare zipfile.BadZipFile -- the same
    "Raises: ValueError" contract every sibling extractor honours for a
    whole-file-open failure."""
    fake_pt = tmp_path / "corrupt_zip.pt"
    fake_pt.write_bytes(b"PK\x03\x04truncated")

    with patch("zipfile.is_zipfile", return_value=True):
        with patch(
            "zipfile.ZipFile", side_effect=_zipfile.BadZipFile("truncated archive")
        ):
            with pytest.raises(ValueError, match="Failed to read PyTorch"):
                read_pytorch(fake_pt)


def test_read_pytorch_raw_pickle_open_oserror(tmp_path: Path) -> None:
    """read_pytorch raises ValueError when the raw pickle file itself can't
    be opened -- matching its own documented "Raises: ValueError: If the
    file cannot be opened" contract, the same one every sibling extractor
    (hdf5.py, numpy.py, ...) honours for a whole-file-open failure (as
    opposed to a single field failing to extract, which degrades
    gracefully instead)."""
    fake_pt = tmp_path / "unreadable.pt"
    fake_pt.write_bytes(b"dummy")

    with patch("zipfile.is_zipfile", return_value=False):
        with patch.object(Path, "open", side_effect=OSError("permission denied")):
            with pytest.raises(ValueError, match="Failed to read PyTorch"):
                read_pytorch(fake_pt)


def test_dotted_name_unrecognized_ast_node() -> None:
    """_dotted_name returns None for AST nodes that are not Name or Attribute."""
    assert _dotted_name(object()) is None


def test_read_pytorch_raw_pickle_with_class(tmp_path: Path) -> None:
    """read_pytorch records type_of_model from raw pickle with class name."""
    fake_pt = tmp_path / "model.pt"
    fake_pt.write_bytes(b"dummy_bytes")

    with patch("zipfile.is_zipfile", return_value=False):
        with patch(
            "pitloom.extract.ai_model.pytorch._fickling_get_top_class",
            return_value="torch.nn.Linear",
        ):
            meta = read_pytorch(fake_pt)
            assert meta.type_of_model == "torch.nn.Linear"
            assert "type_of_model" in meta.provenance


def test_fickling_get_top_class_no_title_case_returns_none() -> None:
    """_fickling_get_top_class returns None when AST has no title-case class names."""
    # pylint: disable=import-outside-toplevel
    import pickle

    data = pickle.dumps({"key": 1, "nested": [2, 3]})
    assert _fickling_get_top_class(_io.BytesIO(data)) is None


def _top_class_of(source: str) -> str | None:
    """:func:`_fickling_get_top_class` of a pickle whose fickling AST is
    *source* (the shape fickling writes, ending ``result = ...``)."""
    # pylint: disable=import-outside-toplevel
    import ast

    from fickling.fickle import Pickled

    fake_pkl = SimpleNamespace(ast=ast.parse(source))
    with patch.object(Pickled, "load", return_value=fake_pkl):
        return _fickling_get_top_class(_io.BytesIO(b"\x80\x02N."))


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        # Protocol 2+: NEWOBJ, followed through aliases past an earlier
        # title-case call building a part of the object.
        (
            "_var0 = Net.__new__(Net)\n_var1 = OrderedDict()\n"
            "_var2 = _var0\nresult = _var2\n",
            "Net",
        ),
        # Protocols 0 and 1: copyreg._reconstructor(cls, base, state).
        ("_var0 = _reconstructor(m.Net, object, None)\nresult = _var0\n", "m.Net"),
        ("result = OrderedDict()\n", "OrderedDict"),
        # A dict checkpoint: no class, even with one inside it.
        ("_var0 = OrderedDict()\nresult = {'model': _var0}\n", None),
        # A pickled class (not an instance), a function's result, an
        # unresolvable callee, a missing name, no result at all.
        ("result = Net\n", None),
        ("result = _rebuild_tensor_v2(1)\n", None),
        ("result = x[0]()\nFoo()\n", None),
        ("result = _var9\n", None),
        ("_reconstructor()\nFoo()\n", None),
        ("result = _reconstructor()\n", None),
        ("_var0 = _var1\n_var1 = _var0\nresult = _var0\n", None),
    ],
    ids=[
        "newobj-alias",
        "reconstructor",
        "plain-call",
        "dict",
        "class",
        "function",
        "subscript",
        "unbound",
        "no-result",
        "reconstructor-no-args",
        "alias-cycle",
    ],
)
def test_top_class_is_the_top_level_objects_class(
    source: str, expected: str | None, caplog: pytest.LogCaptureFixture
) -> None:
    """The class of the object fickling assigns to ``result``, not the
    first title-case call anywhere in the pickle; no shape is a walk
    failure."""
    caplog.set_level(logging.WARNING)
    assert _top_class_of(source) == expected
    assert not caplog.records


@pytest.mark.parametrize(
    ("fixture", "expected"),
    [("example-model.pt", "Linear"), ("example-model.pth", "OrderedDict")],
)
def test_pytorch_fixture_type_of_model(fixture: str, expected: str) -> None:
    """A full-model save names the module class; a state-dict save its
    ``OrderedDict``."""
    pytest.importorskip("fickling.fickle")
    assert read_pytorch(_PYTORCH_DIR / fixture).type_of_model == expected


def test_fickling_get_top_class_ast_walk_failure_logs_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """_fickling_get_top_class logs a warning and returns None if the AST
    walk fails after a successful parse, distinct from a parse failure."""
    # pylint: disable=import-outside-toplevel
    from fickling.fickle import Pickled

    with (
        patch.object(Pickled, "load", return_value=SimpleNamespace(ast=None)),
        caplog.at_level(logging.WARNING, logger="pitloom.extract.ai_model.pytorch"),
    ):
        assert _fickling_get_top_class(_io.BytesIO(b"\x80\x02N.")) is None
    assert any("AST walk failed" in r.message for r in caplog.records)
