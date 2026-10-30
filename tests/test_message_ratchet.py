# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The message ratchet: the number of emission sites in ``src/pitloom`` that
say no catalogued message (no `` [code]``) may only fall, per module and in
total.

A new uncoded site raises its module's count and fails the first test: give
the message a code in :mod:`pitloom.messages`. A coded or removed site lowers
the count below the baseline and fails it too, so the gain is written down:
regenerate the baseline (the failure says how) and commit it.

See also: ``scripts/message_inventory/`` (the tool and what counts),
``tests/fixtures/message-inventory/`` (the baseline),
``tests/scripts/message_inventory/`` (the tool's own tests).
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from typing import Any

import pytest

from tests._message_inventory import REPO_ROOT, load

#: Sites already coded: (file, emitter) of the Git LFS pointer families, of
#: ``over-cap`` (the catalogue's helper, a wrapper of it, and the raises), of
#: the model-stub causes (the scan's lines, the single-file refusal, the
#: missing libraries, the parameter count) and of an unreadable file or an
#: unlistable directory.
CODED_SITES = [
    ("src/pitloom/core/lfs_pointer.py", "emit"),
    ("src/pitloom/core/lfs_pointer.py", "raise"),
    ("src/pitloom/extract/scanner.py", "emit"),
    ("src/pitloom/extract/scanner.py", "warn_over_cap"),
    ("src/pitloom/extract/authors.py", "warn_field_cap"),
    ("src/pitloom/extract/wheel.py", "warn_archive_member_over_cap"),
    ("src/pitloom/extract/project/_sdist_scan.py", "warn_archive_member_over_cap"),
    ("src/pitloom/extract/project/sdist.py", "raise"),
    ("src/pitloom/extract/remote/_git_run.py", "raise"),
    ("src/pitloom/extract/ai_model/reader.py", "raise"),
    ("src/pitloom/assemble/_model_generator.py", "raise"),
    ("src/pitloom/extract/remote/huggingface.py", "raise"),
    ("src/pitloom/cli/commands/utils.py", "print_error"),
    ("src/pitloom/core/_models_wheel_build_subprocess.py", "raise"),
    ("src/pitloom/extract/_file_headers.py", "raise"),
    ("src/pitloom/extract/ai_model/parameter_count.py", "emit"),
    ("src/pitloom/assemble/spdx3/_ai_package.py", "emit"),
    ("src/pitloom/core/_models_wheel.py", "warn_file_unreadable"),
    ("src/pitloom/core/_models_wheel_unlistable.py", "warn_dir_unlistable"),
    ("src/pitloom/core/dataset_hash.py", "warn_dir_unlistable"),
    ("src/pitloom/extract/lock/_lock_io.py", "warn_file_unreadable"),
]


@pytest.fixture(name="records", scope="module")
def records_fixture() -> list[dict[str, Any]]:
    """Every emission site of the repository's own ``src/pitloom``."""
    return load().inventory(REPO_ROOT)  # type: ignore[no-any-return]


def test_no_module_gains_or_silently_loses_an_uncoded_site(
    records: list[dict[str, Any]],
) -> None:
    mi = load()
    text = (REPO_ROOT / mi.BASELINE_PATH).read_text(encoding="utf-8")
    problems = mi.compare(mi.parse_baseline(text), mi.uncoded_counts(records))
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize(
    ("file", "emitter"),
    CODED_SITES,
    ids=[
        "emit",
        "raise",
        "scanner-emit",
        "over-cap",
        "over-cap-wrapper",
        "over-cap-archive-wheel",
        "over-cap-archive-scan",
        "over-cap-sdist",
        "over-cap-git",
        "model-refusal",
        "model-file-refusal",
        "hub-library",
        "validate-library",
        "build-library",
        "magika-library",
        "parameter-count",
        "hyperparameter",
        "file-scan",
        "file-discovery",
        "dataset-dir",
        "lock-file",
    ],
)
def test_the_tool_sees_the_catalogued_sites_as_coded(
    records: list[dict[str, Any]], file: str, emitter: str
) -> None:
    sites = [r for r in records if r["file"] == file and r["emitter"] == emitter]
    assert any(r["coded"] for r in sites)
    assert any(load().in_scope(r) for r in sites if r["coded"])


def test_every_over_cap_call_is_a_coded_site_in_scope(
    records: list[dict[str, Any]],
) -> None:
    """The catalogue's helper says ``over-cap`` at every call, a wrapper's
    call too: each is a site the ratchet counts, and coded, so no count
    rose when the helper moved into the catalogue."""
    helpers = ("warn_over_cap", "warn_field_cap", "warn_archive_member_over_cap")
    sites = [r for r in records if r["helper"] in helpers]
    assert len(sites) > 30  # the scan finds them
    assert all(r["coded"] and load().in_scope(r) for r in sites)


def test_every_call_of_a_read_failure_helper_is_a_coded_site_in_scope(
    records: list[dict[str, Any]],
) -> None:
    """A catalogue helper that says its message through ``emit`` codes each
    caller's line: ``warn_file_unreadable`` and ``warn_dir_unlistable``,
    called from every module that reads a project's, a dataset's or a
    registry's files, each a site the ratchet counts."""
    helpers = ("warn_file_unreadable", "warn_dir_unlistable")
    sites = [r for r in records if r["helper"] in helpers]
    assert len({r["file"] for r in sites}) > 12  # the scan finds them
    assert all(r["coded"] and load().in_scope(r) for r in sites)


@pytest.mark.parametrize(
    "file", ["src/pitloom/core/evidence.py", "src/pitloom/core/provenance.py"]
)
def test_a_programming_error_is_out_of_scope(
    records: list[dict[str, Any]], file: str
) -> None:
    """An ``InternalError`` raise is no message to a user: the ratchet does
    not count it, and the baseline does not rise for it."""
    internal = [
        r
        for r in records
        if r["file"] == file and r.get("exc_class") == "InternalError"
    ]
    assert internal and not any(load().in_scope(r) for r in internal)


def _calls_of(name: str) -> set[str]:
    """The modules of ``src/pitloom`` (POSIX, under it) that call *name*."""
    root = REPO_ROOT / "src" / "pitloom"
    found = set()
    for path in sorted(root.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_bytes())):
            if isinstance(node, ast.Call) and name in (
                getattr(node.func, "id", None),
                getattr(node.func, "attr", None),
            ):
                found.add(path.relative_to(root).as_posix())
    return found


def test_a_model_readers_raise_reaches_a_user_only_through_the_scan(
    records: list[dict[str, Any]],
) -> None:
    """Why a raise in ``extract/ai_model/`` (its dispatch aside) is detail,
    out of scope: only the scanner calls the dispatch, ``read_ai_model``, and
    only the dispatch's registry names a reader, so what a reader raises is
    the ``<error>`` of the scanner's ``model-unreadable`` line (or turned
    into ``library-missing``)."""
    assert _calls_of("read_ai_model") == {"extract/scanner.py"}
    readers = {
        f"read_{name}"
        for name in (
            "crfsuite",
            "fasttext",
            "gguf",
            "hdf5",
            "keras",
            "numpy",
            "onnx",
            "pytorch",
            "pytorch_pt2",
            "safetensors",
        )
    }
    root = REPO_ROOT / "src" / "pitloom"
    for path in sorted(root.rglob("*.py")):
        names = {
            n.id
            for n in ast.walk(ast.parse(path.read_bytes()))
            if isinstance(n, ast.Name)
        }
        rel = path.relative_to(root).as_posix()
        if names & readers:
            assert rel == "extract/ai_model/reader.py", rel
    mi = load()
    sites = [r for r in records if r["file"].startswith(mi.READER_PACKAGE)]
    raised = [r for r in sites if r["emitter"] == "raise"]
    assert len(raised) > 30  # the scan finds them
    for record in raised:
        dispatch = record["file"] == mi.READER_DISPATCH
        assert (mi.reach(record) == "detail") is not dispatch, record["line"]


def test_the_documented_command_runs_the_ratchet() -> None:
    done = subprocess.run(
        [sys.executable, "-m", "scripts.message_inventory", "--check"],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONUTF8": "1"},
        capture_output=True,
        check=False,
        timeout=120,
    )
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    assert done.stdout == b""
