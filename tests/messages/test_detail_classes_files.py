# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``DETAIL_EXC`` cases said from a file: an SBOM, a fragment, an ID
registry, a dataset or a lock file whose read or parse raises one of the
classes, through ``loom id``, the fragment merge, the dataset hash and the
lock cascade.

See also: tests/messages/test_detail_classes.py (the harness and the
meta-tests).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from pitloom.assemble.spdx3.fragments import merge_fragments
from pitloom.core import dataset_hash
from pitloom.core.config import FragmentConfig
from pitloom.core.file_hash import sha256_read
from pitloom.core.project import ProjectMetadata
from pitloom.export.spdx3_json import Spdx3JsonExporter
from pitloom.extract.lock import _lock_io, apply_locked_dependencies
from tests._license_graph import fragment_graph
from tests.messages.test_detail_classes import (
    Case,
    Env,
    Outcome,
    Trigger,
    call,
    cap_reason,
    case_id,
    cli,
    make_env,
    prove,
)

pytestmark = pytest.mark.platform  # files, directories, a mode of 0

#: A mode of 0 holds the user only off Windows and not as root.
_CAN_CHMOD = sys.platform != "win32" and getattr(os, "geteuid", lambda: 1)() != 0
_NS = "https://spdx.org/spdxdocs/frag"
_FRAGMENTS = "src/pitloom/assemble/spdx3/_fragments_read.py"


def _fragment(path: Path, description: str) -> None:
    package = {
        "type": "software_Package",
        "spdxId": f"{_NS}#P",
        "name": "p",
        "description": description,
    }
    path.write_bytes(json.dumps(fragment_graph([package])).encode())


def _merge(env: Env, *names: str) -> Outcome:
    frags = [FragmentConfig(path=name) for name in names]
    return call(env, lambda: merge_fragments(env.tmp, frags, Spdx3JsonExporter()))


def _unread(content: bytes | None) -> Trigger:
    """A fragment holding *content*; ``None``: a directory named as one."""

    def trigger(env: Env) -> Outcome:
        path = env.tmp / "f.json"
        if content is None:
            path.mkdir()
        else:
            path.write_bytes(content)
        return _merge(env, "f.json")

    return trigger


def _not_comparable(text: str) -> Trigger:
    """Two fragments describing one package, once as *text*, once as other
    JSON text: compared as JSON, *text* is none."""

    def trigger(env: Env) -> Outcome:
        _fragment(env.tmp / "a.json", text)
        _fragment(env.tmp / "b.json", '{"a": 1}')
        return _merge(env, "a.json", "b.json")

    return trigger


def _fragment_case(function: str, content: bytes | None, code: str) -> Case:
    return Case(
        "FragmentReadError",
        ("pitloom.messages.fragments", "FragmentReadError"),
        (_FRAGMENTS, function),
        "detail",
        _unread(content),
        code=code,
    )


def _json_case(function: str, text: str) -> Case:
    return Case(
        "_NotComparableJson",
        ("pitloom.assemble.spdx3._fragments_equal", "_NotComparableJson"),
        ("src/pitloom/assemble/spdx3/_fragments_equal.py", function),
        "signal",
        _not_comparable(text),
    )


def _id_import(env: Env) -> Outcome:
    (env.tmp / "s.json").write_bytes(b'{"@graph": [], "n": NaN}')
    return cli(env, "id", "import", env.tmp / "s.json", "-o", env.tmp / "r.json")


def _duplicate_key(env: Env) -> Outcome:
    (env.tmp / "r.json").write_bytes(b'{"a": 1, "a": 2}')
    return cli(
        env, "id", "generate", "--project-dir", env.tmp, "-o", env.tmp / "r.json"
    )


def _hash(env: Env, path: Path) -> Outcome:
    return call(env, lambda: dataset_hash.hash_dataset(path, max_bytes=64))


def _unlistable(env: Env) -> Outcome:
    if not _CAN_CHMOD:
        pytest.skip("a mode of 0 holds no one here")
    (env.tmp / "data" / "sub").mkdir(parents=True)
    (env.tmp / "data" / "a.txt").write_bytes(b"a")
    (env.tmp / "data" / "sub").chmod(0)
    try:
        return _hash(env, env.tmp / "data")
    finally:
        (env.tmp / "data" / "sub").chmod(0o755)


def _grown_file(env: Env) -> Outcome:
    """A file that ``stat()`` says is small and holds more when read."""
    (env.tmp / "d.bin").write_bytes(b"x" * 100)
    env.monkeypatch.setattr(dataset_hash, "_file_size", lambda path: 1)
    return _hash(env, env.tmp / "d.bin")


def _grown_member(env: Env) -> Outcome:
    """A directory's file read within less than its walk left."""
    (env.tmp / "data").mkdir()
    (env.tmp / "data" / "a.bin").write_bytes(b"x" * 10)
    real = sha256_read
    env.monkeypatch.setattr(
        dataset_hash, "sha256_read", lambda member, max_bytes: real(member, max_bytes=1)
    )
    return _hash(env, env.tmp / "data")


def _lock_dir(env: Env) -> Outcome:
    (env.tmp / "pylock.toml").mkdir()
    return call(
        env, lambda: apply_locked_dependencies(ProjectMetadata(name="pkg"), env.tmp)
    )


def _lock_over(env: Env) -> Outcome:
    (env.tmp / "pylock.toml").write_bytes(b'lock-version = "1.0"\n')
    env.monkeypatch.setattr(_lock_io, "FETCH_MAX_BYTES", 8)
    return call(
        env, lambda: apply_locked_dependencies(ProjectMetadata(name="pkg"), env.tmp)
    )


def _budget_case(trigger: Trigger, tag: str) -> Case:
    return Case(
        "ReadBudgetExceeded",
        ("pitloom.core.file_hash", "ReadBudgetExceeded"),
        ("src/pitloom/core/file_hash.py", "_read_chunks"),
        "signal",
        trigger,
        tag=tag,
    )


def _lock_case(kind: str, trigger: Trigger, code: str) -> Case:
    return Case(
        "LockFileRefusedError",
        ("pitloom.extract.lock._lock_io", "LockFileRefusedError"),
        ("src/pitloom/extract/lock/_lock_io.py", "read_lock_bytes"),
        kind,
        trigger,
        code=code,
        payload=cap_reason if kind == "carrier" else None,
    )


CASES = [
    Case(
        "_NonJsonConstant",
        ("pitloom._sbom_format", "_NonJsonConstant"),
        ("src/pitloom/_sbom_format.py", "_reject_constant"),
        "detail",
        _id_import,
        code="json-malformed",
    ),
    _json_case("_no_duplicate_keys", '{"a": 1, "a": 2}'),
    _json_case("_no_constant", '{"a": NaN}'),
    _fragment_case("read_fragment_bytes", None, "fragment-unreadable"),
    _fragment_case("_json_of", b"{not json", "fragment-invalid"),
    _fragment_case("parse_fragment", b"3", "fragment-invalid"),
    Case(
        "_DuplicateKeyError",
        ("pitloom.id_registry._format", "_DuplicateKeyError"),
        ("src/pitloom/id_registry/_format.py", "_unique_keys"),
        "detail",
        _duplicate_key,
        code="registry-malformed",
    ),
    Case(
        "_Unlistable",
        ("pitloom.core.dataset_hash", "_Unlistable"),
        ("src/pitloom/core/dataset_hash.py", "_raise_unlistable"),
        # The line names the directory and the OS's reason from the error
        # the class carries, never the class's own text.
        "carrier",
        _unlistable,
        code="dir-unlistable",
        payload=lambda exc: f"{exc.error.filename}: could not list",
    ),
    _budget_case(_grown_file, "file"),
    _budget_case(_grown_member, "dir"),
    _lock_case("detail", _lock_dir, "file-unreadable"),
    _lock_case("carrier", _lock_over, "over-cap"),
]


@pytest.mark.parametrize("case", CASES, ids=[case_id(c) for c in CASES])
def test_a_detail_class_is_said_by_its_kind(
    case: Case,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    prove(case, make_env(tmp_path, monkeypatch, capsys, caplog))
