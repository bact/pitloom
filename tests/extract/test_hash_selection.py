# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the shared deterministic SHA-256 tie-break
(:mod:`pitloom.extract._hash_selection`), used by both
:mod:`pitloom.assemble.spdx3.deps_pypi` and every per-format lock-hash
extractor.
"""

from pitloom.extract._hash_selection import select_sha256_hash


def test_no_candidates_returns_none() -> None:
    assert select_sha256_hash([]) is None


def test_single_candidate() -> None:
    digest = "a" * 64
    assert select_sha256_hash([("pkg-1.0.tar.gz", digest)]) == digest


def test_wheel_preferred_over_sdist() -> None:
    sdist_digest = "a" * 64
    wheel_digest = "b" * 64
    candidates = [
        ("pkg-1.0.tar.gz", sdist_digest),
        ("pkg-1.0-py3-none-any.whl", wheel_digest),
    ]
    assert select_sha256_hash(candidates) == wheel_digest


def test_multiple_wheels_deterministic_by_filename() -> None:
    """Regardless of input order, the same filename always wins."""
    macos = ("pkg-1.0-cp310-cp310-macosx_10_9_x86_64.whl", "a" * 64)
    linux = ("pkg-1.0-cp310-cp310-manylinux_2_17_x86_64.whl", "b" * 64)
    windows = ("pkg-1.0-cp310-cp310-win_amd64.whl", "c" * 64)

    forward = select_sha256_hash([macos, linux, windows])
    reversed_order = select_sha256_hash([windows, linux, macos])

    assert forward == reversed_order == macos[1]


def test_multiple_wheels_identical_filename_deterministic_by_digest() -> None:
    """When multiple wheel entries share the exact same filename (e.g. pytz
    in pipenv pylock.toml), the tie-break stably sorts by digest."""
    candidate_1 = ("pkg-1.0-py3-none-any.whl", "2" * 64)
    candidate_2 = ("pkg-1.0-py3-none-any.whl", "1" * 64)

    forward = select_sha256_hash([candidate_1, candidate_2])
    reversed_order = select_sha256_hash([candidate_2, candidate_1])

    assert forward == reversed_order == "1" * 64


def test_no_filename_falls_back_to_sorting_digests() -> None:
    """Pipfile.lock's shape: no filenames at all, just a flat hash list."""
    digest_a = "a" * 64
    digest_b = "b" * 64
    candidates = [(None, digest_b), (None, digest_a)]
    assert select_sha256_hash(candidates) == digest_a


def test_named_candidates_preferred_over_nameless() -> None:
    named_digest = "a" * 64
    nameless_digest = "b" * 64
    candidates = [(None, nameless_digest), ("pkg-1.0.tar.gz", named_digest)]
    assert select_sha256_hash(candidates) == named_digest


def test_malformed_digest_is_skipped_not_an_error() -> None:
    valid_digest = "a" * 64
    candidates = [
        ("pkg-1.0.tar.gz", "not-a-valid-digest"),
        ("pkg-1.0-py3-none-any.whl", "too-short"),
        ("pkg-1.0.zip", valid_digest),
    ]
    assert select_sha256_hash(candidates) == valid_digest


def test_all_malformed_returns_none() -> None:
    assert select_sha256_hash([("pkg-1.0.tar.gz", "not-a-digest")]) is None


def test_digest_is_lowercased() -> None:
    digest = "A" * 64
    assert select_sha256_hash([("pkg-1.0.tar.gz", digest)]) == "a" * 64
