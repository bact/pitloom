# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for get_wheel_files()'s skip_merkle_root option.

See also: tests/core/models_wheel/test_models_wheel_files.py for the
scan_file_headers/detect_content_type combinatorial surface this option
interacts with; ``working-docs/design/performance-optimizations.md``
(section "Skip Merkle root in get_wheel_files()") for why this option
exists (embed-wheel's one caller discards the root and the per-file
digest, so hashing every file for them is wasted I/O).
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from hatchling.builders.wheel import WheelBuilder

from pitloom.core.models import get_wheel_files

from ..test_models import _FakeIncludedFile
from .test_models_wheel_files import _make_header_project, _patch_recurse

# ---------------------------------------------------------------------------
# Core contract: skip_merkle_root=True skips the root and every digest,
# without changing which files are discovered or their other fields.
# ---------------------------------------------------------------------------


def test_skip_merkle_root_returns_none_root_and_none_digests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tagged_file, plain_file = _make_header_project(tmp_path)
    _patch_recurse(monkeypatch, tagged_file, plain_file)

    root, files, _ = get_wheel_files(tmp_path, skip_merkle_root=True)

    assert root is None
    assert len(files) == 2
    assert all(f.digest_sha256 is None for f in files)


def test_skip_merkle_root_does_not_change_discovered_file_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The flag must only affect hashing -- same paths, same count, same
    order as a normal (hashing) run on the identical fixture."""
    tagged_file, plain_file = _make_header_project(tmp_path)

    _patch_recurse(monkeypatch, tagged_file, plain_file)
    _root_off, files_off, _ = get_wheel_files(tmp_path)

    _patch_recurse(monkeypatch, tagged_file, plain_file)
    _root_skip, files_skip, _ = get_wheel_files(tmp_path, skip_merkle_root=True)

    assert [f.distribution_path for f in files_off] == [
        f.distribution_path for f in files_skip
    ]
    assert [f.physical_path for f in files_off] == [f.physical_path for f in files_skip]


def test_skip_merkle_root_true_is_not_the_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression guard: the default must stay False, i.e. every existing
    caller that doesn't pass the flag keeps getting real digests/roots."""
    tagged_file, plain_file = _make_header_project(tmp_path)
    _patch_recurse(monkeypatch, tagged_file, plain_file)

    root, files, _ = get_wheel_files(tmp_path)

    assert root is not None
    assert all(f.digest_sha256 is not None for f in files)


# ---------------------------------------------------------------------------
# Regression for the "empty file_entries wrongly empties project_files"
# bug caught during plan review: the emptiness check must key off
# project_files (populated regardless of skip_merkle_root), not the
# now-conditionally-populated file_entries/hash list.
# ---------------------------------------------------------------------------


def test_skip_merkle_root_does_not_silently_drop_discovered_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With 2 real files and skip_merkle_root=True, the naive
    implementation (emptiness check on the never-populated hash list)
    would silently return (None, []) here -- discarding every file every
    single time the flag is used, the opposite of the intended
    optimization. Must actually return both files."""
    tagged_file, plain_file = _make_header_project(tmp_path)
    _patch_recurse(monkeypatch, tagged_file, plain_file)

    _root, files, _ = get_wheel_files(tmp_path, skip_merkle_root=True)

    assert len(files) == 2
    assert {f.distribution_path for f in files} == {"pkg/tagged.py", "pkg/plain.py"}


def test_skip_merkle_root_genuinely_empty_file_set_still_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The flip side of the above: when there truly are zero files, the
    fixed check (keyed on project_files) must still correctly report
    (None, []) -- not accidentally start reporting a phantom non-empty
    result."""
    monkeypatch.setattr(WheelBuilder, "recurse_included_files", lambda _self: iter([]))

    root, files, _ = get_wheel_files(tmp_path, skip_merkle_root=True)

    assert root is None
    assert not files


# ---------------------------------------------------------------------------
# Regression for the "silent read-failure downgrade" bug caught during
# plan review: an unreadable file must still be detected and skipped with
# a warning, matching the skip_merkle_root=False contract, instead of
# silently appearing with digest_sha256=None.
# ---------------------------------------------------------------------------


def test_skip_merkle_root_unreadable_file_is_still_detected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A file that is a regular file but errors on open (permission
    error, TOCTOU race, ...) must still be warned about and skipped --
    the access probe (open+close, no read) taken on the skip_merkle_root
    path must surface the same failure a full read would have."""
    tagged_file, plain_file = _make_header_project(tmp_path)
    _patch_recurse(monkeypatch, tagged_file, plain_file)

    real_open = Path.open

    def _failing_open(self: Path, *args: object, **kwargs: object) -> object:
        if self == plain_file:
            raise PermissionError(f"Simulated permission error: {self}")
        return real_open(self, *args, **kwargs)  # type: ignore[call-overload]

    monkeypatch.setattr(Path, "open", _failing_open)

    root, files, _ = get_wheel_files(tmp_path, skip_merkle_root=True)

    assert root is None
    assert [f.distribution_path for f in files] == ["pkg/tagged.py"]
    assert "FILE=pkg/plain.py: could not read" in caplog.text


def test_skip_merkle_root_false_unreadable_file_is_also_detected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Same scenario with skip_merkle_root=False (the existing, already
    -tested contract via read_bytes()) -- included here so the two are
    directly comparable side by side and drift between them is caught."""
    tagged_file, plain_file = _make_header_project(tmp_path)
    _patch_recurse(monkeypatch, tagged_file, plain_file)

    def _failing_read_bytes(self: Path) -> bytes:
        if self == plain_file:
            raise PermissionError(f"Simulated permission error: {self}")
        return b"value = 1\n"

    monkeypatch.setattr(Path, "read_bytes", _failing_read_bytes)

    root, files, _ = get_wheel_files(tmp_path)

    assert root is not None
    assert [f.distribution_path for f in files] == ["pkg/tagged.py"]
    assert "FILE=pkg/plain.py: could not read" in caplog.text


# ---------------------------------------------------------------------------
# Interaction with scan_file_headers / detect_content_type: skip_merkle_root
# must only govern hashing, never whether bytes are read for the other two
# scanners.
# ---------------------------------------------------------------------------


def test_skip_merkle_root_with_file_header_scanning_still_reads_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """scan_file_headers=True forces a real read regardless of
    skip_merkle_root -- header fields must still populate, while the
    digest itself stays None (skip_merkle_root governs hashing
    independently of *why* bytes were read)."""
    tagged_file, plain_file = _make_header_project(tmp_path)
    _patch_recurse(monkeypatch, tagged_file, plain_file)

    _root, files, _ = get_wheel_files(
        tmp_path, scan_file_headers=True, skip_merkle_root=True
    )

    assert all(f.digest_sha256 is None for f in files)
    tagged = next(f for f in files if f.distribution_path == "pkg/tagged.py")
    assert tagged.copyright_text == "2026 Test Author"
    assert tagged.spdx_license_identifier == "MIT"


def test_skip_merkle_root_with_content_type_detection_still_reads_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same as above for detect_content_type=True."""
    tagged_file, plain_file = _make_header_project(tmp_path)
    _patch_recurse(monkeypatch, tagged_file, plain_file)

    _root, files, _ = get_wheel_files(
        tmp_path,
        detect_content_type=True,
        content_type_method="extension",
        skip_merkle_root=True,
    )

    assert all(f.digest_sha256 is None for f in files)
    for project_file in files:
        assert project_file.content_type is not None


def test_skip_merkle_root_with_no_scanning_does_not_parse_headers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """skip_merkle_root=True with both scanners off (the intended,
    highest-savings case): a file carrying real SPDX tags is not
    header-parsed at all -- proves the file-header/content-type gates
    still independently govern parsing, unaffected by skip_merkle_root,
    and that the b"" placeholder fed to the header/content-type resolver
    on this path never leaks into a populated field."""
    tagged_file, plain_file = _make_header_project(tmp_path)
    _patch_recurse(monkeypatch, tagged_file, plain_file)

    calls: list[str] = []

    def _spy_parse(data: bytes) -> None:
        del data
        calls.append("parse_file_header")

    monkeypatch.setattr("pitloom.extract._file_headers.parse_file_header", _spy_parse)

    _root, files, _ = get_wheel_files(tmp_path, skip_merkle_root=True)

    assert not calls
    tagged = next(f for f in files if f.distribution_path == "pkg/tagged.py")
    assert tagged.copyright_text is None
    assert tagged.spdx_license_identifier is None
    assert tagged.digest_sha256 is None


# ---------------------------------------------------------------------------
# Determinism: skip_merkle_root must not disturb the distribution_path
# sort order that keeps SBOM output bit-for-bit reproducible.
# ---------------------------------------------------------------------------


def test_skip_merkle_root_output_order_is_deterministic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tagged_file, plain_file = _make_header_project(tmp_path)

    def _reverse_order_recurse(_self: WheelBuilder) -> Iterator[_FakeIncludedFile]:
        # Reverse discovery order from the usual fixture helper, to prove
        # the sort -- not accidental discovery order -- is what makes
        # the output stable.
        yield _FakeIncludedFile(str(plain_file), "pkg/plain.py")
        yield _FakeIncludedFile(str(tagged_file), "pkg/tagged.py")

    expected = ["pkg/plain.py", "pkg/tagged.py"]

    monkeypatch.setattr(WheelBuilder, "recurse_included_files", _reverse_order_recurse)
    _root1, files1, _ = get_wheel_files(tmp_path, skip_merkle_root=True)
    assert [f.distribution_path for f in files1] == expected

    monkeypatch.setattr(WheelBuilder, "recurse_included_files", _reverse_order_recurse)
    _root2, files2, _ = get_wheel_files(tmp_path, skip_merkle_root=True)
    assert [f.distribution_path for f in files2] == expected
