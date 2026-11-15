# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`pitloom.id_registry._credentials`: a namespace, a key or
an element id the registry would store as written holds no credential, on
the constructor, ``register()``, ``id import`` and a run's harvest.

See also: tests/test_credential_surfaces.py (the command line and the file)
and tests/core/test_iri_namespace.py (the namespace rule).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.core.iri import require_namespace_iri
from pitloom.core.url_masking import holds_url_credentials
from pitloom.id_registry import FILE_TYPE, IdRegistry
from pitloom.id_registry._harvest import _import_sbom_element
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import code_of

pytestmark = pytest.mark.platform

_SECRET = "S3CRET"
_REGISTRY = "credentials-unsafe/registry"


@pytest.mark.parametrize(
    "namespace",
    [
        f"https://u:{_SECRET}@ids.example/ns",
        f"ssh://{_SECRET}@ids.example/ns",
        "ssh://git@ids.example/ns",
        f"https://ids.example/ns?token={_SECRET}",
    ],
    ids=["userinfo", "user-only", "account", "token"],
)
def test_the_constructor_refuses_a_credentialed_namespace(namespace: str) -> None:
    """Any user information, an account name too: no id is minted in it."""
    makers: list[Callable[[], IdRegistry]] = [
        lambda: IdRegistry(namespace=namespace),
        lambda: IdRegistry.new("demo", namespace=namespace),
    ]
    for make in makers:
        with pytest.raises(ValueError, match="namespace is stored as written") as e:
            make()
        assert code_of(e.value) == _REGISTRY and _SECRET not in str(e.value)


def test_namespaces_kept_alike_once_masked_say_so() -> None:
    """A ``code`` value a namespace keeps is masked in a message, so two
    that differ only there are told apart in words."""
    registry = IdRegistry(namespace="https://h/ns?code=A")
    with pytest.raises(ValueError, match="differ in masked credentials") as e:
        registry.require_namespace("https://h/ns?code=B")
    assert code_of(e.value) == "option-conflict"


@pytest.mark.parametrize(
    ("type_name", "name", "refused"),
    [
        ("software_Package", "git+ssh://git@github.com/o/r", False),
        ("software_Package", "ssh://ghp_TOKEN@github.com/o/r", True),
        ("ai_AIPackage", f"https://u:{_SECRET}@h/m", True),
        (FILE_TYPE, "meet 10:30@ab:c.txt", False),
        (FILE_TYPE, "a@b c.txt", False),
        ("ai_AIPackage", "alice:pw@host:o/r", True),
    ],
    ids=["account", "ssh-token", "userinfo", "odd-file-name", "at-file-name", "scp"],
)
def test_register_refuses_a_credential_key_and_accepts_an_account(
    type_name: str, name: str, refused: bool
) -> None:
    registry = IdRegistry(namespace="https://ids.example/ns")
    if refused:
        with pytest.raises(ValueError, match="key is stored as written") as e:
            registry.register(type_name, name)
        assert code_of(e.value) == _REGISTRY and not registry.elements
    else:
        assert registry.register(type_name, name).startswith("https://ids.example")


def _package(spdx_id: str, name: str) -> spdx3.ai_AIPackage:
    package = spdx3.ai_AIPackage()
    package.spdxId = spdx_id
    package.name = name
    return package


@pytest.mark.parametrize(
    ("spdx_id", "name"),
    [
        ("https://ids.example/ns#P-1", f"https://u:{_SECRET}@h/m"),
        (f"https://u:{_SECRET}@ids.example/ns#P-1", "model"),
    ],
    ids=["key", "id"],
)
def test_a_run_harvest_skips_a_credentialed_key_or_id(
    spdx_id: str, name: str, caplog: pytest.LogCaptureFixture
) -> None:
    registry = IdRegistry(namespace="https://ids.example/ns")
    object_set = spdx3.SHACLObjectSet()
    object_set.add(_package(spdx_id, name))
    with caplog.at_level(logging.WARNING):
        assert registry.harvest(object_set)[0] == 0
    (said,) = caplog.records
    assert getattr(said, CODE_ATTR) == _REGISTRY and _SECRET not in caplog.text
    assert not registry.elements
    assert "stores an element's key and id as written" in said.getMessage()


def test_id_import_keeps_its_namespace_over_a_credentialed_one(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    graph = [
        {
            "type": "CreationInfo",
            "@id": "_:c",
            "specVersion": "3.0.1",
            "createdBy": ["https://x/a"],
            "created": "2026-01-01T00:00:00Z",
        },
        {"type": "SoftwareAgent", "spdxId": "https://x/a", "creationInfo": "_:c"},
        {
            "type": "SpdxDocument",
            "spdxId": f"https://u:{_SECRET}@ids.example/doc",
            "creationInfo": "_:c",
        },
    ]
    sbom = tmp_path / "s.json"
    context = "https://spdx.org/rdf/3.0.1/spdx-context.jsonld"
    sbom.write_text(json.dumps({"@context": context, "@graph": graph}), "utf-8")
    registry = IdRegistry(namespace="https://ids.example/own")
    with caplog.at_level(logging.WARNING):
        registry.import_sbom(sbom)
    assert registry.namespace == "https://ids.example/own"
    assert "holds user information or a secret query value" in caplog.text
    assert _SECRET not in caplog.text


@pytest.mark.parametrize(
    "value",
    [
        f"alice:{_SECRET}@host:o/r",
        f"alice:{_SECRET}@host:/srv/r",
        f"https://h/ns?hmac={_SECRET}",
    ],
    ids=["scp", "scp-absolute", "hmac"],
)
def test_a_value_stored_as_written_refuses_every_credential_shape(value: str) -> None:
    """A namespace and a registry key are refused, masked."""
    assert holds_url_credentials(value)
    with pytest.raises(ValueError) as caught:
        require_namespace_iri(value)
    assert _SECRET not in str(caught.value)
    with pytest.raises(ValueError):
        IdRegistry.new("demo", namespace="https://ids.example/ns").register(
            "ai_AIPackage", value
        )


def test_a_weak_name_is_kept_in_a_namespace_and_a_key() -> None:
    """``code``, ``session``... are accepted as written (they are often no
    secret), the same rule as in an SBOM."""
    value = "https://h/ns?code=utf8&session=2024"
    assert not holds_url_credentials(value)
    assert require_namespace_iri(value) == value


def test_harvest_skips_a_credential_id_and_keeps_an_odd_file_name(
    caplog: pytest.LogCaptureFixture,
) -> None:
    registry = IdRegistry.new("demo", namespace="https://ids.example/ns")
    package = _package(f"https://u:{_SECRET}@ex.org/ns#Pkg-1?token={_SECRET}", "model")
    skipped = _package("https://ids.example/ns#P-2", f"https://u:{_SECRET}@h/m")
    odd = spdx3.software_File()
    odd.spdxId = "https://ids.example/ns#File-1"
    odd.name = "a@b c.txt"
    with caplog.at_level(logging.WARNING):
        for element in (package, skipped, odd):
            _import_sbom_element(registry, element)
    assert "skipped" in caplog.text and _SECRET not in caplog.text
    assert len(registry.elements) == 1
    assert registry.register(FILE_TYPE, "a@b c.txt")
