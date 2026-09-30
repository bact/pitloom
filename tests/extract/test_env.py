# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.extract.env.read_environment()."""

import json
import subprocess
from collections.abc import Sequence
from importlib.metadata import version as dist_version
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from pitloom.extract.env import read_environment


def _fake_pipdeptree_result(
    tree: Sequence[object],
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["pipdeptree", "--json"],
        returncode=0,
        stdout=json.dumps(tree),
        stderr="",
    )


def test_read_environment_provenance_distinguishes_synthetic_from_tool() -> None:
    """name/version are Pitloom's own synthetic root, not something
    pipdeptree reported -- only dependencies is genuinely sourced from it."""
    tree = [{"package": {"key": "requests", "package_name": "requests"}}]
    with patch("subprocess.run", return_value=_fake_pipdeptree_result(tree)):
        metadata, returned_tree = read_environment()

    assert metadata.name == "deployed-environment"
    assert returned_tree == tree
    assert "pipdeptree" not in metadata.provenance["name"]
    assert "Pitloom generator" in metadata.provenance["name"]
    assert "pipdeptree" not in metadata.provenance["version"]
    assert metadata.provenance["dependencies"] == "Source: pipdeptree"


def test_read_environment_pipdeptree_missing_raises() -> None:
    """A missing pipdeptree executable surfaces as a clear RuntimeError."""
    with patch("subprocess.run", side_effect=FileNotFoundError("pipdeptree")):
        try:
            read_environment()
        except RuntimeError as exc:
            assert "pipdeptree" in str(exc)
        else:
            raise AssertionError("expected RuntimeError")


FIXTURES = Path(__file__).parent.parent / "fixtures" / "pipdeptree"
_JSON_FIXTURE = FIXTURES / "requests-2.34.2.json"
_JSON_TREE_FIXTURE = FIXTURES / "requests-2.34.2.json-tree.json"


def _result_of(stdout: bytes | str) -> subprocess.CompletedProcess[Any]:
    return subprocess.CompletedProcess(
        args=["pipdeptree", "--json"], returncode=0, stdout=stdout, stderr=b""
    )


def test_read_environment_runs_flat_json_not_json_tree() -> None:
    """The assembler consumes ``--json``; ``--json-tree`` is another shape."""
    with patch(
        "subprocess.run", return_value=_result_of(_JSON_FIXTURE.read_bytes())
    ) as run:
        read_environment()

    argv = run.call_args.args[0]
    assert argv[1:] == ["-m", "pipdeptree", "--json"]


def test_read_environment_real_json_output() -> None:
    """Captured real ``pipdeptree --json`` output is accepted as is."""
    with patch("subprocess.run", return_value=_result_of(_JSON_FIXTURE.read_bytes())):
        _, tree = read_environment()

    assert [n["package"]["key"] for n in tree] == [
        "certifi",
        "charset-normalizer",
        "idna",
        "requests",
        "urllib3",
    ]
    requests = next(n for n in tree if n["package"]["key"] == "requests")
    assert [d["key"] for d in requests["dependencies"]] == [
        "certifi",
        "charset-normalizer",
        "idna",
        "urllib3",
    ]


def test_read_environment_rejects_real_json_tree_output() -> None:
    """The old ``--json-tree`` shape is a read failure, not "unknown"."""
    with patch(
        "subprocess.run", return_value=_result_of(_JSON_TREE_FIXTURE.read_bytes())
    ):
        with pytest.raises(RuntimeError, match="Unexpected pipdeptree output"):
            read_environment()


_MALFORMED = {
    "not-a-list": b'{"package": {"key": "a"}}',
    "node-not-a-dict": b'["a"]',
    "no-package": b'[{"key": "a", "dependencies": []}]',
    "package-not-a-dict": b'[{"package": "a"}]',
    "key-not-a-string": b'[{"package": {"key": 1}}]',
    "dependencies-not-a-list": b'[{"package": {"key": "a"}, "dependencies": {}}]',
    "dependency-without-key": (
        b'[{"package": {"key": "a"}, "dependencies": [{"package_name": "b"}]}]'
    ),
    "invalid-json": b"Traceback (most recent call last)",
    "empty": b"",
    "invalid-utf8": b"[\xff]",
}


@pytest.mark.parametrize("stdout", _MALFORMED.values(), ids=_MALFORMED.keys())
def test_read_environment_malformed_output_raises(stdout: bytes) -> None:
    with patch("subprocess.run", return_value=_result_of(stdout)):
        with pytest.raises(RuntimeError, match="Unexpected pipdeptree output"):
            read_environment()


def test_read_environment_empty_list_is_an_empty_environment() -> None:
    """Zero packages is a valid answer, not a read failure."""
    with patch("subprocess.run", return_value=_result_of(b"[]")):
        _, tree = read_environment()

    assert tree == []


def test_read_environment_accepts_utf8_bom() -> None:
    with patch("subprocess.run", return_value=_result_of(b"\xef\xbb\xbf[]")):
        _, tree = read_environment()

    assert tree == []


@pytest.mark.parametrize(
    "error",
    [
        subprocess.CalledProcessError(1, ["pipdeptree"]),
        PermissionError("denied"),
    ],
    ids=["nonzero-exit", "oserror"],
)
def test_read_environment_run_failure_raises(error: Exception) -> None:
    with patch("subprocess.run", side_effect=error):
        with pytest.raises(RuntimeError, match="Failed to run pipdeptree"):
            read_environment()


def test_read_environment_run_failure_names_the_stderr_cause() -> None:
    error = subprocess.CalledProcessError(
        1, ["pipdeptree"], stderr=b"Traceback ...\nNo module named pipdeptree\n"
    )
    with patch("subprocess.run", side_effect=error):
        with pytest.raises(RuntimeError, match="No module named pipdeptree"):
            read_environment()


def test_read_environment_orders_packages_and_dependencies_by_key() -> None:
    """Output order is pipdeptree's, so it is fixed here, not assumed."""

    def pkg(key: str, deps: tuple[str, ...] = ()) -> dict[str, Any]:
        return {
            "package": {"key": key, "installed_version": "1"},
            "dependencies": [{"key": d} for d in deps],
        }

    shuffled = [pkg("zeta", ("y", "b")), pkg("alpha"), pkg("mid")]
    with patch(
        "subprocess.run", return_value=_result_of(json.dumps(shuffled).encode())
    ):
        _, tree = read_environment()

    keys = [n["package"]["key"] for n in tree]
    assert keys == ["alpha", "mid", "zeta"]
    assert keys != [n["package"]["key"] for n in shuffled]
    assert [d["key"] for d in tree[2]["dependencies"]] == ["b", "y"]


def test_read_environment_live_names_installed_packages() -> None:
    """Real pipdeptree on this interpreter: no ``unknown`` package."""
    _, tree = read_environment()

    names = [n["package"].get("package_name") for n in tree]
    assert names
    assert "unknown" not in names
    pytest_node = next(n for n in tree if n["package"]["key"] == "pytest")
    assert pytest_node["package"]["installed_version"] == dist_version("pytest")


def test_read_environment_breaks_key_ties_by_version_then_name() -> None:
    nodes = [
        {"package": {"key": "a", "installed_version": "2", "package_name": "A"}},
        {"package": {"key": "a", "installed_version": "1", "package_name": "b"}},
        {"package": {"key": "a", "installed_version": "1", "package_name": "A"}},
    ]
    with patch("subprocess.run", return_value=_result_of(json.dumps(nodes).encode())):
        _, tree = read_environment()

    assert [
        (n["package"]["installed_version"], n["package"]["package_name"]) for n in tree
    ] == [
        ("1", "A"),
        ("1", "b"),
        ("2", "A"),
    ]
