# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A ``.keras`` archive member that does not parse (invalid, not an object,
not UTF-8, too deep, a byte order mark, ``null``): one warning, the other
member kept.

See also: test_keras_config.py (``compile_config``),
test_keras_config_members.py (``metadata.json`` and the model config) and
test_keras.py (the reader and the fixture).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from pitloom.extract.ai_model import hdf5_config
from tests.extract.ai_model._keras_helpers import META, MODEL, read

_MODEL_FIELDS = (
    "type_of_model, name, hyperparameters, inputs, properties.layer_count, "
    "properties.optimizer, properties.loss, properties.metrics"
)
# How the parser fails on this many unclosed brackets depends on the Python
# build (a recursion error, or a plain syntax error where the C stack is
# deep enough), so only the stub test below pins the recursion wording.
_DEEP = 100_000


_UNPARSED = [
    pytest.param(b"{not valid json", "is not valid JSON (", id="invalid"),
    pytest.param(b"[1, 2]", "is not a JSON object", id="list"),
    pytest.param(b'{"a": "\xff"}', "is not valid JSON ('utf-8' codec", id="utf8"),
    pytest.param(b"[" * _DEEP, "is not valid JSON (", id="unclosed-deep"),
]


@pytest.mark.parametrize(("body", "error"), _UNPARSED)
def test_a_config_that_does_not_parse_keeps_the_metadata(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, body: bytes, error: str
) -> None:
    meta, messages = read(tmp_path, caplog, body, META)
    (message,) = messages
    assert message.startswith(f"config.json {error}")
    assert message.endswith(
        f"; the other archive members are read | Field(s) affected (skipped): "
        f"{_MODEL_FIELDS}"
    )
    assert meta.format_info.framework_version == "3.5.0"
    assert meta.properties["date_saved"] == META["date_saved"]
    assert meta.type_of_model is None and not meta.hyperparameters


@pytest.mark.parametrize(("body", "error"), _UNPARSED)
def test_metadata_that_does_not_parse_keeps_the_config(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, body: bytes, error: str
) -> None:
    meta, messages = read(tmp_path, caplog, MODEL, body)
    (message,) = messages
    assert message.startswith(f"metadata.json {error}")
    assert message.endswith("(skipped): framework_version, properties.date_saved")
    assert (meta.type_of_model, meta.name) == ("Sequential", "m")
    assert meta.hyperparameters == {"units": 2}
    assert meta.format_info.framework_version is None


_TOO_DEEP = b"too-deep"  # a body the stubbed parser cannot take


@pytest.mark.parametrize("member", ["config.json", "metadata.json"])
def test_a_member_too_deep_for_the_parser_is_one_warning(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    member: str,
) -> None:
    """The parser's recursion guard firing is one warning that keeps the other
    member. The guard is stubbed, since where a real parser reaches it
    depends on the Python build."""
    real_loads = json.loads

    def loads(raw: Any, *args: Any, **kwargs: Any) -> Any:
        if raw == _TOO_DEEP:
            raise RecursionError("maximum recursion depth exceeded")
        return real_loads(raw, *args, **kwargs)

    monkeypatch.setattr(hdf5_config, "json", SimpleNamespace(loads=loads))
    config, metadata = (
        (_TOO_DEEP, META) if member == "config.json" else (MODEL, _TOO_DEEP)
    )
    meta, messages = read(tmp_path, caplog, config, metadata)
    (message,) = messages
    assert message.startswith(f"{member} is not valid JSON (nested too deeply); ")
    assert "the other archive members are read" in message
    if member == "config.json":
        assert meta.format_info.framework_version == "3.5.0"
        assert meta.type_of_model is None
    else:
        assert (meta.type_of_model, meta.name) == ("Sequential", "m")
        assert meta.format_info.framework_version is None


@pytest.mark.parametrize(
    "body",
    [
        b"\xef\xbb\xbf" + json.dumps(MODEL).encode(),
        json.dumps(MODEL).encode("utf-16"),
    ],
    ids=["utf-8-bom", "utf-16"],
)
def test_a_config_with_a_byte_order_mark_isread(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, body: bytes
) -> None:
    meta, messages = read(tmp_path, caplog, body)
    assert messages == []
    assert (meta.type_of_model, meta.name) == ("Sequential", "m")


def test_a_null_member_is_no_data(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    meta, messages = read(tmp_path, caplog, b"null", b"null")
    assert messages == []
    assert meta.type_of_model is None and meta.format_info.framework_version is None


def test_a_config_nested_deeply_is_read_without_a_crash(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Deep values where a scalar or a collection is read: the hyperparameter
    is skipped (not a scalar) and the loss is kept as its JSON text, with no
    warning.

    The depth parses on every supported Python: on 3.10 and 3.11 the json
    module counts nesting against the recursion limit, so 1000 levels fail to
    encode or decode there. A document too deep for the parser is the ``deep``
    case of the member-warning test above."""
    deep: Any = []
    for _ in range(300):
        deep = [deep]
    config = {
        "class_name": "Sequential",
        "config": {
            "name": "m",
            "deep": deep,
            "layers": [{"class_name": "Dense", "config": {"deep": deep}}],
        },
        "compile_config": {"loss": deep, "metrics": ["acc"]},
    }
    meta, messages = read(tmp_path, caplog, config)
    assert (meta.type_of_model, meta.name) == ("Sequential", "m")
    assert "deep" not in meta.hyperparameters
    assert meta.properties["metrics"] == '["acc"]'
    assert messages == []
    assert meta.properties["loss"].startswith("[[[[")
    assert meta.properties["layer_count"] == "1"
