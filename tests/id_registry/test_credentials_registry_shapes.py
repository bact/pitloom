# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Every ID registry surface refuses the credential shapes the whole-value
detector added (an access token in a URL, a credential percent-encoded in a
PURL qualifier, a dotless scp-style address) alike, saying the value masked
and never as written.

See also: test_credentials_registry.py in this folder (the user information
and query shapes on the same surfaces).
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.core.url_masking import holds_url_credentials, masked_given_path
from pitloom.id_registry import IdRegistry
from pitloom.id_registry._credentials import (
    id_holds_credentials,
    key_holds_credentials,
)
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import code_of
from tests.core.url_masking._probe_corpus import encoded

pytestmark = pytest.mark.platform

_NS = "https://ids.example/ns"
_REGISTRY = "credentials-unsafe/registry"
_TOKEN = "T0KEN" + "aB3" * 10 + "x"
#: Each shape and the raw text no surface may say.
_SHAPES = {
    "token": (f"https://h.example/m/ghp_{_TOKEN}", _TOKEN),
    "encoded-purl": (
        "pkg:generic/m?download_url=https%3A%2F%2Fu%3AS3CRET%40h%2Fx",
        "S3CRET",
    ),
    "dotless-scp": ("alice:S3CRET@host:repo", "S3CRET"),
    "embedded-url": ("urn:x:https://u:S3CRET@h.example/ns", "S3CRET"),
    "nesting-17": ("https://h.example/x?q=" + "1?" * 17 + "S3CRET", "S3CRET"),
    "encoded-6": (
        "pkg:generic/m?download_url=" + encoded("https://u:S3CRET@h/x", 6),
        encoded("S3CRET", 6),
    ),
}
_PARAMS = pytest.mark.parametrize(
    ("key", "raw"), list(_SHAPES.values()), ids=list(_SHAPES)
)


def _shown(text: str, key: str, raw: str) -> None:
    """*text* names *key* masked and holds nothing of *raw*."""
    assert masked_given_path(key) in text and raw not in text


@_PARAMS
def test_load_refuses_the_file_and_leaves_it_as_it_was(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, key: str, raw: str
) -> None:
    path = tmp_path / "ids.json"
    elements = {key: {"spdxId": f"{_NS}#AIPackage-1"}}
    document = {
        "elements": {"ai_AIPackage": elements},
        "id_counters": {"AIPackage": 1},
        "namespace": _NS,
        "project_root": ".",
        "version": 4,
    }
    path.write_text(json.dumps(document), "utf-8")
    before = path.read_bytes()
    with caplog.at_level(logging.WARNING), pytest.raises(ValueError) as caught:
        IdRegistry.load(path, refuse_credentials=True)
    assert path.read_bytes() == before and not caplog.records
    assert code_of(caught.value) == _REGISTRY
    _shown(str(caught.value), key, raw)


@_PARAMS
def test_harvest_skips_the_element(
    caplog: pytest.LogCaptureFixture, key: str, raw: str
) -> None:
    package = spdx3.ai_AIPackage()
    package.spdxId = f"{_NS}#P-1"
    package.name = key
    object_set = spdx3.SHACLObjectSet()
    object_set.add(package)
    registry = IdRegistry(namespace=_NS)
    with caplog.at_level(logging.WARNING):
        assert registry.harvest(object_set)[0] == 0
    assert not registry.elements
    (said,) = caplog.records
    assert getattr(said, CODE_ATTR) == _REGISTRY
    _shown(caplog.text, key, raw)


def _run(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(  # nosec B603
        [sys.executable, "-m", "pitloom", *args],
        capture_output=True,
        check=False,
        timeout=120,
        cwd=tmp_path,
    )


@_PARAMS
def test_cli_e_refuses_and_id_import_skips(tmp_path: Path, key: str, raw: str) -> None:
    """``loom id generate -e --refuse-url-credentials`` refuses the key
    with exit 1 and writes no registry; ``loom id import`` of an SBOM
    element with that key skips it (in either mode), and neither says the
    key as written."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_bytes(b"x\n")
    done = _run(
        tmp_path,
        *("id", "generate", "-o", "r.json", "-e", f"{key}:ai_AIPackage", "src"),
        "--refuse-url-credentials",
    )
    err = done.stderr.decode()
    assert done.returncode == 1 and f"[{_REGISTRY}]" in err
    _shown(err, key, raw)
    assert not (tmp_path / "r.json").exists()
    info: dict[str, object] = {"type": "CreationInfo", "@id": "_:c"}
    info |= {"specVersion": "3.0.1", "createdBy": ["https://x/a"]}
    info |= {"created": "2026-01-01T00:00:00Z"}
    graph = [
        info,
        {"type": "SoftwareAgent", "spdxId": "https://x/a", "creationInfo": "_:c"},
        {
            "type": "ai_AIPackage",
            "spdxId": f"{_NS}#M-1",
            "creationInfo": "_:c",
            "name": key,
            "software_packageVersion": "1",
        },
    ]
    context = "https://spdx.org/rdf/3.0.1/spdx-context.jsonld"
    document = {"@context": context, "@graph": graph}
    (tmp_path / "s.json").write_text(json.dumps(document), "utf-8")
    done = _run(tmp_path, "id", "import", "s.json", "-o", "r2.json")
    err = done.stderr.decode()
    assert done.returncode == 0 and f"[{_REGISTRY}]" in err
    _shown(err, key, raw)
    assert raw not in (tmp_path / "r2.json").read_text("utf-8")


@pytest.mark.parametrize(
    ("type_name", "held"),
    [("software_File", False), ("software_Package", True)],
    ids=["file", "package"],
)
def test_a_file_key_is_no_scp_address(type_name: str, held: bool) -> None:
    """A file name with no space that reads as ``user:password@host:path``
    is a path for a File key, an address for any other key."""
    assert key_holds_credentials(type_name, "meet-10:30@ab:c.txt") is held


@pytest.mark.parametrize(
    "key",
    ["urn:x:https://u:S3CRET@h/ns", "src/https:/u:S3CRET@h/x", "a/ghp_" + _TOKEN],
    ids=["urn", "file-path", "token"],
)
def test_a_url_inside_a_registry_value_is_refused(key: str) -> None:
    """A registry value is an identifier, never prose: a URL or a token
    anywhere in it is read, though a URL-typed value elsewhere is read only
    as a whole."""
    assert key_holds_credentials("software_File", key)
    assert not holds_url_credentials(key)


_NAMESPACES = {
    "token": f"https://ids.example/ns/ghp_{_TOKEN}",
    "embedded-url": "urn:x:https://u:S3CRET@ids.example/ns",
    "nesting-17": "https://ids.example/ns?q=" + "1?" * 17 + "S3CRET",
}


@pytest.mark.parametrize("namespace", list(_NAMESPACES.values()), ids=list(_NAMESPACES))
def test_every_namespace_surface_refuses_the_shape(
    tmp_path: Path, namespace: str
) -> None:
    """``IdRegistry(namespace=...)``, a registry file's namespace and
    ``loom id generate --namespace`` each refuse the namespace, never
    saying it as written; the command with the library's code."""
    with pytest.raises(ValueError) as caught:
        IdRegistry(namespace=namespace)
    assert code_of(caught.value) == _REGISTRY
    path = tmp_path / "ids.json"
    document = {"namespace": namespace, "project_root": ".", "version": 4}
    path.write_text(json.dumps(document), "utf-8")
    with pytest.raises(ValueError) as caught:
        IdRegistry.load(path)
    assert code_of(caught.value) == "registry-malformed"
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_bytes(b"x\n")
    done = _run(tmp_path, "id", "generate", "--namespace", namespace, "src")
    err = done.stderr.decode()
    assert done.returncode == 1 and "S3CRET" not in err and _TOKEN not in err
    assert err.endswith(f" [{_REGISTRY}]\n")  # the library's code


def test_an_element_id_with_a_url_inside_it_is_refused() -> None:
    assert id_holds_credentials("urn:x:https://u:S3CRET@h/ns#x")
    assert not id_holds_credentials("urn:x:ns#x")
