# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""An input given that Pitloom cannot use: an SBOM whose ``@graph`` is not
a list of objects (``sbom-invalid``), a Hugging Face target that is no Hub
URL or model id (``hf-url-invalid``), each a coded, trusted line.

See also: tests/assemble/test_embed_unusable_sbom.py (``json-malformed``,
``sbom-wrong-format`` and ``file-unreadable/not-utf8`` for an SBOM),
tests/cli/test_cli_project_git_url.py (``target-wrong-format``).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.extract.remote.huggingface import read_huggingface
from pitloom.id_registry._sbom_read import read_sbom_objects
from pitloom.messages.targets import (
    HF_URL_INVALID,
    SBOM_INVALID,
)
from tests._message_drift import raised_as

pytestmark = pytest.mark.platform


@pytest.mark.parametrize(
    ("graph", "said"),
    [
        (b'{"@graph": {}}', "SBOM @graph is not a list"),
        (b'{"@graph": [1]}', "SBOM @graph holds an element that is not an object"),
        (
            b'{"@graph": [{"software_downloadLocation": "https://u:S3CRETX@h/x",'
            b' "software_downloadLocation": "https://h/x"}]}',
            "SBOM holds an object with a key given twice",
        ),
        (
            b'{"a": 1, "a": 1, "@graph": []}',
            "SBOM holds an object with a key given twice",
        ),
    ],
    ids=["not-list", "element", "duplicate-key", "duplicate-equal"],
)
def test_an_sbom_graph_of_the_wrong_shape_is_sbom_invalid(
    tmp_path: Path, graph: bytes, said: str
) -> None:
    sbom = tmp_path / "a b.json"
    sbom.write_bytes(graph)
    with pytest.raises(ValueError) as caught:
        read_sbom_objects(sbom)
    assert str(caught.value) == f"FILE={sbom}: {said}"
    assert raised_as(caught.value, SBOM_INVALID)
    assert caught.value.__cause__ is None and "S3CRETX" not in str(caught.value)


def test_a_memory_error_in_the_sbom_reader_is_not_sbom_invalid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Running out of memory is the machine's, not a verdict on the SBOM."""
    sbom = tmp_path / "ok.json"
    sbom.write_bytes(b'{"@graph": []}')

    def _out_of_memory(*_args: object, **_kwargs: object) -> None:
        raise MemoryError

    monkeypatch.setattr(spdx3.JSONLDDeserializer, "read", _out_of_memory)
    with pytest.raises(MemoryError):
        read_sbom_objects(sbom)


@pytest.mark.parametrize(
    "source",
    ["/not/a/hub/model", "https://u:secret@example.org/a\nb"],
    ids=["path", "credentials-newline"],
)
def test_a_target_that_is_no_hub_model_is_hf_url_invalid(source: str) -> None:
    with pytest.raises(ValueError) as caught:
        read_huggingface(source)
    assert "secret" not in str(caught.value) and "\n" not in str(caught.value)
    assert str(caught.value).endswith(": not a valid Hugging Face URL or model ID")
    assert raised_as(caught.value, HF_URL_INVALID)
