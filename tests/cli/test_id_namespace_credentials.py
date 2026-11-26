# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A registry namespace holding a credential is refused with one code on
the command line (``loom id generate --namespace``) and in the library
(``IdRegistry(namespace=...)``): ``credentials-unsafe/registry``, the token
masked on both.

See also: tests/cli/test_cli_id_namespace_root.py (a namespace that is no
IRI, still argparse's refusal), tests/test_credential_surfaces.py (every
registry surface).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.id_registry import IdRegistry
from pitloom.messages import MESSAGES, code_of
from tests._message_drift import raised_as

_TOKEN = "ghp_" + "a" * 36
_NS = f"https://user:{_TOKEN}@example.com/ns"
_CODE = "credentials-unsafe/registry"


@pytest.mark.parametrize("existing", [False, True], ids=["new", "existing"])
def test_a_credentialed_namespace_has_the_librarys_code_on_the_cli(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    existing: bool,
) -> None:
    """The command refuses it before reading a file, a new registry or an
    existing one, with the library's line and code; nothing is written."""
    registry = tmp_path / "ids.json"
    if existing:
        IdRegistry.new("demo", namespace="urn:demo").save(registry)
    before = registry.read_bytes() if existing else None
    monkeypatch.chdir(tmp_path)
    argv = ["loom", "id", "generate", "--namespace", _NS, "-o", str(registry)]
    monkeypatch.setattr(sys, "argv", argv)
    assert __main__.main() == 1
    out, err = capsys.readouterr()
    assert _TOKEN not in out + err
    with pytest.raises(ValueError) as library:
        IdRegistry.new("demo", namespace=_NS)
    assert code_of(library.value) == _CODE and _TOKEN not in str(library.value)
    assert raised_as(library.value, MESSAGES[_CODE])
    assert err == f"ERROR: loom id generate: {library.value} [{_CODE}]\n"
    assert (registry.read_bytes() if existing else registry.exists()) == (
        before if existing else False
    )
