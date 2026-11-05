# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``library-unusable``: a library that is installed but fails
to import is told from one that is not installed, by every import Pitloom
makes of an optional library (the model readers, the Hub client, magika).

See also: tests/test_library_unusable_surfaces.py (the surfaces) and
tests/core/test_optional_libraries.py (the libraries).
"""

# pylint: disable=protected-access

from __future__ import annotations

import copy
import importlib
import logging
import pickle  # nosec B403
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from types import ModuleType
from typing import cast

import pytest

from pitloom.cli.commands import utils
from pitloom.core.ai_metadata import AiModelFormat
from pitloom.core.optional_libraries import (
    HUB,
    MAGIKA,
    Requirement,
    import_failed,
    not_installed,
)
from pitloom.extract import _file_headers
from pitloom.extract.ai_model import read_ai_model
from pitloom.extract.ai_model.reader_requirements import REQUIREMENTS
from pitloom.extract.remote.huggingface import read_huggingface
from pitloom.extract.scanner import read_model_candidate
from pitloom.extract.scanner_project import local_model_candidate
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import (
    LIBRARY_MISSING,
    LIBRARY_UNUSABLE,
    code_of,
    trusted_message,
)
from tests._message_drift import raised_as

_FAKE = Requirement("pitloom_fake_lib", "fake")
_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "aimodels"
#: What a broken install's import raises.
_BROKEN = "OSError('libfake.so: cannot open shared object file')"


@pytest.mark.parametrize(
    ("exc", "missing"),
    [
        (
            ModuleNotFoundError(
                "No module named 'pitloom_fake_lib'", name=_FAKE.module
            ),
            True,
        ),
        (ModuleNotFoundError("x", name=f"{_FAKE.module}.sub"), False),
        (ModuleNotFoundError("No module named 'dep'", name="dep"), False),
        (ModuleNotFoundError("x", name=f"{_FAKE.module}_other"), False),
        (ModuleNotFoundError("x"), False),
        (ImportError("cannot import name 'Reader'", name=_FAKE.module), False),
        (OSError("libfake.so"), False),
        (RuntimeError("bad build"), False),
    ],
    ids=["module", "submodule", "dependency", "prefix", "no-name", "name", "os", "rt"],
)
def test_only_the_module_itself_missing_is_not_installed(
    exc: BaseException, missing: bool
) -> None:
    error = import_failed(_FAKE, exc)
    assert not_installed(_FAKE, exc) is missing
    entry = LIBRARY_MISSING if missing else LIBRARY_UNUSABLE
    assert code_of(error) == entry.code and raised_as(error, entry)


def test_the_error_names_the_module_what_it_raised_and_the_extra() -> None:
    error = import_failed(_FAKE, OSError("libfake.so:\ncannot open"))
    assert str(error) == (
        "required library failed to import: pitloom_fake_lib: libfake.so: cannot "
        "open; reinstall pitloom[fake]"
    )
    for kept in (copy.copy(error), pickle.loads(pickle.dumps(error))):  # nosec B301
        assert str(kept) == str(error) and code_of(kept) == code_of(error)


def test_a_none_in_sys_modules_is_not_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, _FAKE.module, cast(ModuleType, None))
    with pytest.raises(ImportError) as caught:
        importlib.import_module(_FAKE.module)
    assert code_of(import_failed(_FAKE, caught.value)) == LIBRARY_MISSING.code


@pytest.fixture(name="broken")
def fixture_broken(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Callable[..., None]]:
    """Makes a module importable from a package whose import raises."""

    def make(module: str, raised: str = _BROKEN) -> None:
        package = tmp_path / "site" / module
        package.mkdir(parents=True)
        (package / "__init__.py").write_bytes(f"raise {raised}\n".encode())
        for name in [n for n in sys.modules if n.partition(".")[0] == module]:
            monkeypatch.delitem(sys.modules, name)
        importlib.invalidate_caches()

    monkeypatch.syspath_prepend(str(tmp_path / "site"))
    yield make
    importlib.invalidate_caches()


_READERS = [
    (AiModelFormat.ONNX, "onnx/light-inception-v2.onnx"),
    (AiModelFormat.GGUF, "gguf/stories260K.gguf"),
    (AiModelFormat.SAFETENSORS, "safetensors/phi-tiny-random.safetensors"),
    (AiModelFormat.HDF5, "hdf5/example-model.h5"),
    (AiModelFormat.FASTTEXT, "fasttext/sentimentdemo.bin"),
    (AiModelFormat.NUMPY, "numpy/example-model-v1.npy"),
]


@pytest.mark.parametrize(("fmt", "fixture"), _READERS, ids=str)
def test_a_reader_whose_library_is_broken_is_a_stub_saying_so(
    fmt: AiModelFormat,
    fixture: str,
    broken: Callable[..., None],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The library is installed (``find_spec`` finds it) but its import
    raises: the reader's error, and the scan's line, name what it raised."""
    requirement = REQUIREMENTS[fmt]
    broken(requirement.module)
    path = _FIXTURES / fixture
    with pytest.raises(ImportError) as caught:
        read_ai_model(path, model_format=fmt)
    assert raised_as(caught.value, LIBRARY_UNUSABLE)
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        meta = read_model_candidate(local_model_candidate(path))
    assert not meta.provenance  # a stub
    (record,) = [r for r in caplog.records if hasattr(r, CODE_ATTR)]
    assert getattr(record, CODE_ATTR) == LIBRARY_UNUSABLE.code
    assert record.getMessage() == (
        f"FORMAT={fmt} FILE={path}: required library failed to import: "
        f"libfake.so: cannot open shared object file; reinstall {requirement.spec}"
    )


@pytest.mark.parametrize(
    ("module", "fmt", "fixture", "name"),
    [
        ("h5py", AiModelFormat.HDF5, "hdf5/example-model.h5", "dep"),
        (
            "onnx",
            AiModelFormat.ONNX,
            "onnx/light-inception-v2.onnx",
            "onnx.onnx_cpp2py_export",
        ),
    ],
    ids=["dependency", "own-submodule"],
)
def test_a_library_missing_a_module_it_imports_is_unusable(
    module: str,
    fmt: AiModelFormat,
    fixture: str,
    name: str,
    broken: Callable[..., None],
) -> None:
    """The package imported, so it is installed: a module it imports in
    turn, its own extension included, is missing."""
    broken(module, f"ModuleNotFoundError(\"No module named '{name}'\", name={name!r})")
    with pytest.raises(ImportError) as caught:
        read_ai_model(_FIXTURES / fixture, model_format=fmt)
    assert code_of(caught.value) == LIBRARY_UNUSABLE.code
    assert str(caught.value).endswith(
        f": No module named '{name}'; reinstall {REQUIREMENTS[fmt].spec}"
    )


def test_a_broken_hub_client_is_said_before_any_fetch(
    broken: Callable[..., None],
) -> None:
    broken(HUB.module)
    with pytest.raises(ImportError) as caught:
        read_huggingface("google-bert/bert-base-uncased")
    assert raised_as(caught.value, LIBRARY_UNUSABLE)
    assert str(caught.value).startswith(
        "required library failed to import: huggingface_hub: libfake.so"
    )


def test_a_broken_magika_is_said_once_and_falls_back_per_file(
    broken: Callable[..., None],
) -> None:
    broken(MAGIKA.module)
    _file_headers._get_magika.cache_clear()
    try:
        causes = []
        for _ in range(2):
            with pytest.raises(ImportError) as caught:
                _file_headers.require_magika_available()
            assert raised_as(caught.value, LIBRARY_UNUSABLE)
            causes.append(caught.value.__cause__)
        assert isinstance(causes[0], OSError) and causes[1] is causes[0]  # cached
        guessed = _file_headers.guess_content_type(b"x", "a.py", method="magika")
        assert guessed == ("text/x-python", "extension_guess")
    finally:
        _file_headers._get_magika.cache_clear()


@pytest.mark.parametrize("kind", ["missing", "broken"])
def test_a_validator_that_cannot_be_imported_says_which(
    kind: str,
    broken: Callable[..., None],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    if kind == "broken":
        broken("spdx3_validate")
    else:
        monkeypatch.setitem(sys.modules, "spdx3_validate", cast(ModuleType, None))
    assert utils._import_spdx3_validate() is None
    entry = LIBRARY_MISSING if kind == "missing" else LIBRARY_UNUSABLE
    (line,) = capsys.readouterr().err.splitlines()
    assert trusted_message(line) is entry
