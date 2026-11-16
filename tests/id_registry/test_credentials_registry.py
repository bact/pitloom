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
import traceback
from collections.abc import Callable
from pathlib import Path

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.core.iri import (
    NAMESPACE_CHARACTER,
    NAMESPACE_CREDENTIALS,
    namespace_problem,
    require_namespace_iri,
)
from pitloom.core.url_masking import holds_url_credentials
from pitloom.id_registry import FILE_TYPE, IdRegistry, save_registry
from pitloom.id_registry._credentials import (
    key_holds_credentials,
    require_key_without_credentials,
)
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
    registry = IdRegistry(namespace="https://ids.example/ns", refuse_credentials=True)
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


def test_a_run_harvest_keeps_an_id_minted_from_an_ssh_account(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The id an SBOM writes for a model named by an ``ssh`` account (weak
    there) is harvested, as its key is; with a password it is skipped."""
    name = "ssh://git@github.com/o/m"
    kept = IdRegistry(namespace="https://ids.example/ns")
    kept_set = spdx3.SHACLObjectSet()
    kept_set.add(_package(f"https://ids.example/ns/{name}#P-1", name))
    with caplog.at_level(logging.WARNING):
        assert kept.harvest(kept_set)[0] == 1
    assert not caplog.records
    skipped = IdRegistry(namespace="https://ids.example/ns")
    skipped_set = spdx3.SHACLObjectSet()
    skipped_set.add(_package(f"https://ids.example/ns/ssh://git:{_SECRET}@h#P", "m"))
    assert skipped.harvest(skipped_set)[0] == 0


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
    assert "holds user information, a secret query value" in caplog.text
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
        IdRegistry.new(
            "demo", namespace="https://ids.example/ns", refuse_credentials=True
        ).register("ai_AIPackage", value)


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


def _registry_file(path: Path, namespace: str, key: str, spdx_id: str) -> Path:
    """A registry file holding *key* -> *spdx_id* and a clean entry."""
    elements = {key: {"spdxId": spdx_id}, "ok": {"spdxId": f"{namespace}#AIPackage-3"}}
    path.write_text(
        json.dumps(
            {
                "elements": {"ai_AIPackage": elements},
                "id_counters": {"AIPackage": 3},
                "namespace": namespace,
                "project_root": ".",
                "version": 4,
            }
        ),
        "utf-8",
    )
    return path


_NS = "https://ids.example/ns"


@pytest.mark.parametrize(
    ("key", "spdx_id"),
    [
        (f"https://u:{_SECRET}@h/m", f"{_NS}#AIPackage-1"),
        ("model", f"https://u:{_SECRET}@ids.example/ns#AIPackage-1"),
        ("model", f"{_NS}#AIPackage-1?token={_SECRET}"),
    ],
    ids=["key", "id", "id-token"],
)
def test_load_refuses_a_credentialed_entry_and_leaves_the_file_alone(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, key: str, spdx_id: str
) -> None:
    """Nothing is dropped or rewritten: the file is not loaded, the error
    names the file and the value masked, and the bytes stay as they were."""
    path = _registry_file(tmp_path / "ids.json", _NS, key, spdx_id)
    before = path.read_bytes()
    with caplog.at_level(logging.WARNING), pytest.raises(ValueError) as caught:
        IdRegistry.load(path, refuse_credentials=True)
    assert code_of(caught.value) == _REGISTRY
    assert _SECRET not in str(caught.value) and "ids.json" in str(caught.value)
    assert "not loaded" in str(caught.value)
    assert not caplog.records
    assert path.read_bytes() == before


def test_load_refuses_a_file_whose_namespace_holds_credentials(
    tmp_path: Path,
) -> None:
    namespace = f"https://u:{_SECRET}@ids.example/ns"
    path = _registry_file(tmp_path / "ids.json", namespace, "m", f"{namespace}#P-1")
    with pytest.raises(ValueError, match="holds user information") as caught:
        IdRegistry.load(path)
    assert _SECRET not in str(caught.value)


def test_a_rebase_refuses_an_entry_another_run_saved_meanwhile(
    tmp_path: Path,
) -> None:
    """The refusal leaves the object as it was and the file byte-identical:
    the save does not happen."""
    path = _registry_file(tmp_path / "ids.json", _NS, "model", f"{_NS}#AIPackage-1")
    registry = IdRegistry.load(path, refuse_credentials=True)
    registry.register("ai_AIPackage", "new")
    _registry_file(path, _NS, f"https://u:{_SECRET}@h/m", f"{_NS}#AIPackage-1")
    before = path.read_bytes()
    held = dict(registry.elements)
    with pytest.raises(ValueError) as caught:
        save_registry(registry)
    assert code_of(caught.value) == _REGISTRY and _SECRET not in str(caught.value)
    assert registry.elements == held
    assert path.read_bytes() == before


_WIDE = {
    "s3-one-slash": f"s3:/u:{_SECRET}@h.example/x",
    "git-https-one-slash": f"git+https:/{_SECRET}@h.example/x",
    "ssh-backslashes": f"ssh:\\\\u:{_SECRET}@h.example/x",
    "git-backslashes": f"git:\\\\u:{_SECRET}@h/x",
    "s3-query": f"s3:/h.example/x?access_token={_SECRET}",
}


@pytest.mark.parametrize("value", list(_WIDE.values()), ids=list(_WIDE))
def test_a_scheme_after_one_separator_is_refused_on_every_surface(value: str) -> None:
    """A URL a masker reads after one ``/`` or after backslashes is refused
    as a namespace, a key and a file's key (a file name holds no scp-style
    address, but a URL), each shown masked."""
    # An IRI holds no backslash: such a namespace is refused for that first.
    assert namespace_problem(value) == (
        NAMESPACE_CHARACTER if "\\" in value else NAMESPACE_CREDENTIALS
    )
    assert holds_url_credentials(value)
    for type_name in ("software_Package", FILE_TYPE):
        assert key_holds_credentials(type_name, value)
        with pytest.raises(ValueError) as e:
            require_key_without_credentials(type_name, value)
        assert _SECRET not in str(e.value) and _SECRET not in repr(e.value.args)


_GHP = "ghp_T0KEN" + "aB3" * 10 + "x"
_LEAKS = {
    "token-in-path": (f"https://h.example/{_GHP}", _GHP[4:]),
    "encoded-qualifier": (
        "pkg:generic/x?download_url=https%3A%2F%2Fu%3AS3CRET%40h%2Fx",
        _SECRET,
    ),
}


@pytest.mark.parametrize(("value", "raw"), list(_LEAKS.values()), ids=list(_LEAKS))
def test_a_refusal_never_shows_what_it_refuses(value: str, raw: str) -> None:
    """A token and a credential encoded in a PURL qualifier are refused as a
    namespace and a key; the message, its arguments and its traceback hold
    neither, and the condition names an access token."""
    errors: list[ValueError] = []
    for refuse in (
        lambda: require_namespace_iri(value),
        lambda: require_key_without_credentials("software_Package", value),
    ):
        with pytest.raises(ValueError) as e:
            refuse()
        errors.append(e.value)
    for error in errors:
        assert "an access token" in str(error)
        assert raw not in str(error) and raw not in repr(error.args)
        assert raw not in "".join(traceback.format_exception(error))
