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
    ],
    ids=["not-list", "element"],
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
