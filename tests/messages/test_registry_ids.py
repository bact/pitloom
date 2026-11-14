# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The ID registry's id and key codes on real call sites: an element named
as given (a URL's credentials masked, a control character escaped, once,
on one line), a PATH as typed (a Windows path as written), the registry
file in a mint refusal as typed, and each line said once per input.

See also: tests/messages/test_registry_file.py (the registry file's own
codes), tests/messages/test_summaries.py (the uncoded summaries).
"""

from __future__ import annotations

import logging
from pathlib import Path, PureWindowsPath

import pytest

from pitloom._loom_caller import warn_registry_miss
from pitloom.core.given_path import GivenPath, TypedPath
from pitloom.id_registry import DATASET_PACKAGE_TYPE, FILE_TYPE, IdRegistry
from pitloom.id_registry._counters import MAX_ID_NUMBER
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import CodedValueError, code_of, emit
from pitloom.messages.id_registry_ids import INDEX_PATH_NO_EFFECT, SKIPPED_PATH_LINE
from pitloom.messages.options import OPTION_INVALID, REGISTRY_PATH_OUTSIDE_LINE
from tests.registry_helpers import make_registry

pytestmark = pytest.mark.platform

_LOG = logging.getLogger("pitloom.test_registry_ids")
_NS = "https://spdx.org/spdxdocs/test-1"


def _said(caplog: pytest.LogCaptureFixture) -> list[tuple[str, str]]:
    return [(r.getMessage(), getattr(r, CODE_ATTR, "")) for r in caplog.records]


@pytest.mark.parametrize(
    ("name", "shown"),
    [
        ("https://u:SECRET@h/d.csv", "https://***:***@h/d.csv"),
        ("data/t\n\x1b.csv", "'data/t\\n\\x1b.csv'"),
        ("C:\\proj\\d.csv", "C:\\proj\\d.csv"),
    ],
    ids=["url-masked", "control", "windows"],
)
def test_a_miss_names_the_element_as_given(
    caplog: pytest.LogCaptureFixture, name: str, shown: str
) -> None:
    registry = make_registry({(DATASET_PACKAGE_TYPE, name): (f"{_NS}#D-1", "0" * 64)})

    with caplog.at_level(logging.WARNING, logger="pitloom.loom"):
        warn_registry_miss(registry, DATASET_PACKAGE_TYPE, name)
        warn_registry_miss(registry, FILE_TYPE, name)

    assert _said(caplog) == [
        (
            f"ID registry: dataset package {shown}: its SHA-256 no longer "
            "matches the entry; minting a new spdxId",
            "registry-hash-conflict",
        ),
        (
            f"ID registry: file {shown} not found; minting a new spdxId",
            "registry-entry-missing",
        ),
    ]


def test_changed_content_escapes_the_name_on_one_line(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The key ``register`` logs was written raw: a newline forged a line."""
    registry = IdRegistry(namespace=_NS)
    old = registry.register(FILE_TYPE, "a\nINFO: forged", sha256="0" * 64)

    with caplog.at_level(logging.INFO, logger="pitloom.id_registry"):
        registry.register(FILE_TYPE, "a\nINFO: forged", sha256="1" * 64)

    assert _said(caplog) == [
        (
            "ID registry: content changed for 'a\\nINFO: forged'; minting a new "
            f"spdxId (old: {old})",
            "registry-hash-conflict",
        )
    ]


@pytest.mark.parametrize(
    ("path", "shown"),
    [
        (PureWindowsPath(r"C:\proj\build\a.py"), r"'C:\proj\build\a.py'"),
        (TypedPath(GivenPath("/abs/build", "./build/../build")), "'./build/../build'"),
        ("build/a\x1b.py", "'build/a\\x1b.py'"),
    ],
    ids=["windows", "typed", "control"],
)
def test_a_path_line_names_the_path_as_typed(
    caplog: pytest.LogCaptureFixture, path: object, shown: str
) -> None:
    with caplog.at_level(logging.WARNING, logger=_LOG.name):
        emit(
            _LOG,
            INDEX_PATH_NO_EFFECT,
            logging.WARNING,
            line=SKIPPED_PATH_LINE,
            path=path,
            name="build",
        )
    exc = CodedValueError(
        OPTION_INVALID, line=REGISTRY_PATH_OUTSIDE_LINE, path=path, root="/p"
    )

    assert _said(caplog) == [
        (
            f"ID registry: PATH {shown} is under a skipped directory name (build); "
            "not indexed",
            "index-path-no-effect",
        )
    ]
    assert str(exc) == f"ID registry: PATH {shown} is not inside the project root '/p'"


def test_a_skipped_path_is_said_once_per_path_given(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "a.py").write_bytes(b"x = 1\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "b.py").write_bytes(b"y = 1\n")
    registry = IdRegistry.new("proj")

    with caplog.at_level(logging.WARNING, logger="pitloom.id_registry"):
        registry.generate([tmp_path / "build", tmp_path / "src"], tmp_path)

    (said,) = _said(caplog)
    assert said[1] == "index-path-no-effect"
    assert "(build); not indexed" in said[0]
    assert [key for _, key in registry.elements] == ["src/b.py"]


def test_a_mint_refusal_names_the_registry_file_as_typed(tmp_path: Path) -> None:
    typed = TypedPath(GivenPath(tmp_path / "r.json", "./x/../r.json"))
    registry = IdRegistry(
        namespace=_NS, path=typed, id_counters={"File": MAX_ID_NUMBER}
    )

    with pytest.raises(ValueError) as caught:
        registry.register(FILE_TYPE, "a")

    assert str(caught.value) == (
        f"ID registry: FILE=./x/../r.json: no File id left to mint in {_NS}"
    )
    assert code_of(caught.value) == "registry-malformed"
