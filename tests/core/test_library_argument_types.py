# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A library argument of the wrong type raises a
:class:`~pitloom.messages.CodedTypeError`; one of the right type that the
parameter does not take, a :class:`~pitloom.messages.CodedValueError`. Both
are ``option-invalid`` and say ``<parameter>: must be X, got Y``; never a
plain ``TypeError`` or ``ValueError``.

See also: tests/core/test_bool_arguments.py (every ``bool`` parameter).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pitloom._embed_wheel import embed_sbom_in_wheel
from pitloom._wheel_sbom_location import find_embedded_sbom
from pitloom.assemble import (
    enrich_model,
    generate,
    generate_merged_sbom,
    generate_model_sbom,
    generate_project_sbom,
    generate_wheel_sbom,
)
from pitloom.core.build_options import BuildOptions
from pitloom.core.config import PitloomConfig
from pitloom.core.creation import Creator, Tool
from pitloom.core.credential_policy import CredentialPolicy
from pitloom.core.fetch_policy import RemoteFetchPolicy
from pitloom.embed import embed_wheel_sbom
from pitloom.id_registry import IdRegistry, resolve_registry
from pitloom.messages import CodedTypeError, CodedValueError, code_of
from tests.argument_errors import enter_loom_run

#: Paths and a ``chdir`` per case: run on every OS.
pytestmark = pytest.mark.platform

#: Values of the wrong type, typed ``Any`` so a call needs no ignore.
_FIVE: Any = 5
_NINE: Any = "9"
_NINETY: Any = "90"
_BYTES: Any = b"r.json"
_FALSE: Any = "false"

#: A wheel that is not there: each check runs before it is read.
_WHEEL = Path("gone-1.0-py3-none-any.whl")

_Call = Callable[[], object]

#: case -> (the call with a wrong type, the line it says)
_WRONG_TYPE: dict[str, tuple[_Call, str]] = {
    "build-timeout": (
        lambda: BuildOptions(timeout=_NINETY),
        "BuildOptions.timeout: must be an integer, got a string '90'",
    ),
    "build-timeout-bool": (
        lambda: BuildOptions(timeout=True),
        "BuildOptions.timeout: must be an integer, got a boolean true",
    ),
    "registry-path": (
        lambda: IdRegistry.load(_BYTES),
        "path: must be a path (a str or an os.PathLike), got a value of type bytes",
    ),
    "policy-refuse": (
        lambda: CredentialPolicy(refuse=1),  # type: ignore[arg-type]
        "CredentialPolicy.refuse: must be True or False, got an integer 1",
    ),
    "creator-name": (
        lambda: Creator(name=_FIVE),
        "Creator.name: must be a non-empty string, got an integer 5",
    ),
    "creator-type": (
        lambda: Creator(name="A", type=_FIVE),
        "Creator.type: must be a string, got an integer 5",
    ),
    "tool-name": (
        lambda: Tool(name=_FIVE),
        "Tool.name: must be a non-empty string, got an integer 5",
    ),
    "provenance-format": (
        lambda: PitloomConfig(provenance_format=_FIVE).provenance,
        "PitloomConfig.provenance_format: must be one of annotation, both, "
        "comment, got an integer 5",
    ),
    "url-credentials": (
        lambda: PitloomConfig(url_credentials=_FIVE),
        'PitloomConfig.url_credentials: must be "warn" or "refuse", got an integer',
    ),
    "config-basename": (
        lambda: PitloomConfig(sbom_basename=_FIVE),
        "PitloomConfig.sbom_basename: must be a file name, not a path, "
        "got an integer 5",
    ),
    "embed-basename": (
        lambda: embed_wheel_sbom(_WHEEL, sbom_basename=_FIVE),
        "sbom_basename: must be a file name, not a path, got an integer 5",
    ),
    "content-type-method": (
        lambda: generate_project_sbom(".", content_type_method=_FIVE),
        "content_type_method: must be one of auto, extension, magika, got an integer 5",
    ),
    "download-cap": (
        lambda: generate_project_sbom(".", max_download_bytes=_NINE),
        "max_download_bytes: must be an integer, got a string '9'",
    ),
    "embed-sbom-filename": (
        lambda: embed_sbom_in_wheel(_WHEEL, "{}", sbom_filename=_FIVE),
        "sbom_filename: must be a file name, not a path, got an integer 5",
    ),
    "find-sbom-filename": (
        lambda: find_embedded_sbom(_WHEEL, _FIVE),
        "sbom_filename: must be a file name, not a path, got an integer 5",
    ),
    "fetch-offline": (
        lambda: RemoteFetchPolicy(offline=_FALSE),
        "RemoteFetchPolicy.offline: must be True or False, got a string 'false'",
    ),
    "loom-config": (
        lambda: enter_loom_run(pitloom_config=_FIVE),
        "pitloom_config: must be a path to a configuration file, or a "
        "PitloomConfig, got an integer 5",
    ),
    "registry-generate-paths": (
        lambda: IdRegistry.new("p").generate(_NINE, Path(".")),
        "paths: must be a list or tuple of paths, got a string '9'",
    ),
    "register-type": (
        lambda: IdRegistry.new("p").register(_FIVE, "x"),
        "type_name: must be a string, got an integer 5",
    ),
    "register-name": (
        lambda: IdRegistry.new("p").register("software_File", _FIVE),
        "name: must be a string, got an integer 5",
    ),
    "register-sha256": (
        lambda: IdRegistry.new("p").register("software_File", "x", sha256=_FIVE),
        "sha256: must be a SHA-256 in hex (64 characters), got an integer 5",
    ),
}

#: case -> (the call with a path argument that is no path, the parameter):
#: refused before :func:`os.fspath` or :class:`pathlib.Path` sees it.
_NOT_A_PATH: dict[str, tuple[_Call, str]] = {
    "config-registry": (
        lambda: PitloomConfig(id_registry=_FIVE),
        "PitloomConfig.id_registry",
    ),
    "embed-sbom": (lambda: embed_wheel_sbom(_WHEEL, sbom_path=_FIVE), "sbom_path"),
    "generate-target": (lambda: generate(_FIVE, output_path=Path("o.json")), "target"),
    "project-target": (lambda: generate_project_sbom(_FIVE), "project_target"),
    "model-source": (lambda: generate_model_sbom(_FIVE), "source"),
    "enrich-source": (lambda: enrich_model(_FIVE), "source"),
    "wheel": (lambda: generate_wheel_sbom(_FIVE), "wheel_path"),
    "embed-wheel": (lambda: embed_wheel_sbom(_FIVE), "wheel_path"),
    "merge": (lambda: generate_merged_sbom(_FIVE), "fragments_dir"),
    "output": (lambda: generate_project_sbom(".", output_path=_FIVE), "output_path"),
    "generate-registry": (
        lambda: generate(".", output_path=Path("o.json"), id_registry=_FIVE),
        "id_registry",
    ),
    "resolve-registry": (lambda: resolve_registry(_FIVE, None, None), "id_registry"),
    "generate-project-dir": (
        lambda: generate(".", output_path=Path("o.json"), project_dir=_FIVE),
        "project_dir",
    ),
    "embed-project-dir": (
        lambda: embed_wheel_sbom(_WHEEL, project_dir=_FIVE),
        "project_dir",
    ),
    "enrich-project": (
        lambda: enrich_model("m.gguf", project_target=_FIVE),
        "project_target",
    ),
    "embed-in-wheel": (lambda: embed_sbom_in_wheel(_FIVE, "{}"), "wheel_path"),
    "registry-new": (lambda: IdRegistry.new("p", path=_FIVE), "path"),
    "registry-root": (lambda: IdRegistry.new("p", project_root=_FIVE), "project_root"),
    "registry-save": (lambda: IdRegistry.new("p").save(_FIVE), "path"),
    "registry-import": (
        lambda: IdRegistry.new("p").import_sbom(_FIVE),
        "sbom_path",
    ),
    "find-sbom-wheel": (lambda: find_embedded_sbom(_FIVE), "wheel_path"),
    "registry-init": (
        lambda: IdRegistry(namespace="https://example.org/ns/", path=_FIVE),
        "path",
    ),
    "registry-generate": (
        lambda: IdRegistry.new("p").generate([_FIVE], Path(".")),
        "paths",
    ),
    "registry-generate-root": (
        lambda: IdRegistry.new("p").generate([], _FIVE),
        "project_root",
    ),
    "registry-generate-exclude": (
        lambda: IdRegistry.new("p").generate([], Path("."), exclude=_FIVE),
        "exclude",
    ),
}

#: case -> (the call with a value of the right type it does not take, the
#: line): the other half of each split above.
_WRONG_VALUE: dict[str, tuple[_Call, str]] = {
    "build-timeout": (
        lambda: BuildOptions(timeout=0),
        "build timeout must be 1-604800 seconds, got 0",
    ),
    "creator-name": (
        lambda: Creator(name=" "),
        "Creator.name: must be a non-empty string, got a string ' '",
    ),
    "tool-name": (
        lambda: Tool(name=""),
        "Tool.name: must be a non-empty string, got a string ''",
    ),
    "provenance-format": (
        lambda: PitloomConfig(provenance_format="x").provenance,
        "PitloomConfig.provenance_format: must be one of annotation, both, "
        "comment, got a string 'x'",
    ),
    "url-credentials": (
        lambda: PitloomConfig(url_credentials="x"),
        'PitloomConfig.url_credentials: must be "warn" or "refuse", got a string',
    ),
    "content-type-method": (
        lambda: generate_project_sbom(".", content_type_method="x"),
        "content_type_method: must be one of auto, extension, magika, got a string 'x'",
    ),
    "download-cap": (
        lambda: generate_project_sbom(".", max_download_bytes=0),
        "max_download_bytes: must be an integer of at least 1, got an integer 0",
    ),
    "register-type-empty": (
        lambda: IdRegistry.new("p").register("", "x"),
        "type_name: must be a non-empty string, got a string ''",
    ),
    "register-name-empty": (
        lambda: IdRegistry.new("p").register("software_File", ""),
        "name: must be a non-empty string, got a string ''",
    ),
    "register-type-blank": (
        lambda: IdRegistry.new("p").register(" ", "x"),
        "type_name: must be a non-empty string, got a string ' '",
    ),
}


def _run(call: _Call, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """*call* from an empty directory (holding a project, as ``.`` names)."""
    (tmp_path / "pyproject.toml").write_bytes(b'[project]\nname = "p"\nversion = "1"\n')
    monkeypatch.chdir(tmp_path)
    call()


@pytest.mark.parametrize(
    ("call", "said"), list(_WRONG_TYPE.values()), ids=list(_WRONG_TYPE)
)
def test_a_wrong_type_is_a_coded_type_error(
    call: _Call, said: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(CodedTypeError) as caught:
        _run(call, tmp_path, monkeypatch)
    assert code_of(caught.value) == "option-invalid"
    assert str(caught.value) == said


@pytest.mark.parametrize(
    ("call", "parameter"), list(_NOT_A_PATH.values()), ids=list(_NOT_A_PATH)
)
def test_a_path_argument_that_is_no_path_is_a_coded_type_error(
    call: _Call, parameter: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(CodedTypeError) as caught:
        _run(call, tmp_path, monkeypatch)
    assert code_of(caught.value) == "option-invalid"
    assert str(caught.value) == (
        f"{parameter}: must be a path (a str or an os.PathLike), got an integer 5"
    )


@pytest.mark.parametrize(
    ("call", "said"), list(_WRONG_VALUE.values()), ids=list(_WRONG_VALUE)
)
def test_a_wrong_value_is_a_coded_value_error(
    call: _Call, said: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(CodedValueError) as caught:
        _run(call, tmp_path, monkeypatch)
    assert not isinstance(caught.value, TypeError)
    assert code_of(caught.value) == "option-invalid"
    assert str(caught.value) == said


def test_embedded_sbom_content_of_the_wrong_type(tmp_path: Path) -> None:
    """Refused before the wheel is written (it is not even opened)."""
    wheel = tmp_path / "w-1.0-py3-none-any.whl"
    wheel.write_bytes(b"")
    with pytest.raises(CodedTypeError) as caught:
        embed_sbom_in_wheel(wheel, _FIVE)
    assert str(caught.value) == (
        "sbom_content: must be an SBOM, not empty or white space only, got an integer 5"
    )
    assert wheel.read_bytes() == b""


def test_saving_a_registry_with_no_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``save()`` with no path for a registry made without one: the
    ``registry-file-missing`` cause, as a library error, nothing written."""
    monkeypatch.chdir(tmp_path)
    registry = IdRegistry(namespace="https://example.org/ns/")
    with pytest.raises(CodedValueError) as caught:
        registry.save()
    assert code_of(caught.value) == "registry-file-missing"
    assert str(caught.value) == (
        "ID registry: no file to save to; pass save(path), or create the "
        "registry with a path"
    )
    assert not list(tmp_path.iterdir())


def test_register_takes_a_blank_name(tmp_path: Path) -> None:
    """Only ``""`` names no element: a file may be named white space, so a
    blank name is registered (the other side of ``register-name-empty``)."""
    registry = IdRegistry.new("p", tmp_path / "r.json")
    assert registry.register("software_File", " ").endswith("#File-1")
