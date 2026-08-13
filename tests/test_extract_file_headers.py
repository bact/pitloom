# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for per-file SPDX header tag parsing and content-type detection."""

import sys

import pytest

from pitloom.core.content_type_config import ContentTypeOverride
from pitloom.extract._file_headers import (
    FileHeaderMetadata,
    _get_magika,
    guess_content_type,
    parse_file_header,
    require_magika_available,
    resolve_content_type_override,
)


@pytest.fixture(autouse=True)
def _clear_magika_cache() -> None:
    """``_get_magika()`` caches its instance for process lifetime; clear it
    around every test so ``monkeypatch.setitem(sys.modules, "magika",
    None)`` in one test can't leak a stale cached instance into another."""
    _get_magika.cache_clear()


# ---------------------------------------------------------------------------
# parse_file_header
# ---------------------------------------------------------------------------


def test_parse_file_header_spdx_tags_all_four_present() -> None:
    """All four SPDX-File* tags are read from a Python-style comment header."""
    data = (
        b"# SPDX-FileContributor: Arthit Suriyawongkul\n"
        b"# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul\n"
        b"# SPDX-FileType: SOURCE\n"
        b"# SPDX-License-Identifier: Apache-2.0\n"
    )
    result = parse_file_header(data)
    assert result == FileHeaderMetadata(
        copyright_text="2026-present Arthit Suriyawongkul",
        copyright_source="spdx_tag",
        file_contributors=["Arthit Suriyawongkul"],
        file_type="SOURCE",
        spdx_license_identifier="Apache-2.0",
    )


def test_parse_file_header_multiple_contributors() -> None:
    """Every SPDX-FileContributor line is collected, in order."""
    data = (
        b"# SPDX-FileContributor: Alice\n"
        b"# SPDX-FileContributor: Bob\n"
        b"# SPDX-FileContributor: Carol\n"
        b"# SPDX-License-Identifier: MIT\n"
    )
    result = parse_file_header(data)
    assert result is not None
    assert result.file_contributors == ["Alice", "Bob", "Carol"]


def test_parse_file_header_bare_copyright_fallback() -> None:
    """A bare 'Copyright (c) ...' line is used when no SPDX tag exists."""
    data = b"# Copyright (c) 2024 Joshua Watt\n#\n# SPDX-License-Identifier: MIT\n"
    result = parse_file_header(data)
    assert result is not None
    assert result.copyright_text == "Copyright (c) 2024 Joshua Watt"
    assert result.copyright_source == "bare_copyright_line"
    assert result.spdx_license_identifier == "MIT"


def test_parse_file_header_spdx_tag_wins_over_bare_line() -> None:
    """When both an SPDX tag and a redundant bare line are present, the
    tag wins and the value is recorded exactly once, not duplicated."""
    data = (
        b"# SPDX-FileCopyrightText: 2017 Rohit Lodha\n"
        b"# Copyright (c) 2017 Rohit Lodha\n"
        b"# SPDX-License-Identifier: Apache-2.0\n"
    )
    result = parse_file_header(data)
    assert result is not None
    assert result.copyright_text == "2017 Rohit Lodha"
    assert result.copyright_source == "spdx_tag"


def test_parse_file_header_java_docblock_syntax() -> None:
    """Java-doc '/** ... * ... */' comment blocks are handled without any
    per-language comment-syntax awareness."""
    data = (
        b"/**\n"
        b" * SPDX-FileCopyrightText: Copyright (c) 2011 Source Auditor Inc.\n"
        b" * SPDX-FileType: SOURCE\n"
        b" * SPDX-License-Identifier: Apache-2.0\n"
        b" * <p>\n"
        b' *   Licensed under the Apache License, Version 2.0 (the "License");\n'
        b" *   you may not use this file except in compliance with the License.\n"
        b" */\n"
    )
    result = parse_file_header(data)
    assert result is not None
    assert result.copyright_text == "Copyright (c) 2011 Source Auditor Inc."
    assert result.copyright_source == "spdx_tag"
    assert result.file_type == "SOURCE"
    assert result.spdx_license_identifier == "Apache-2.0"


def test_parse_file_header_shell_shebang_plus_hash() -> None:
    """A shebang line doesn't get mistaken for a tag, and the following
    '#'-comment tag is still found."""
    data = b"#!/usr/bin/env python\n# SPDX-License-Identifier: MIT\nprint(1)\n"
    result = parse_file_header(data)
    assert result is not None
    assert result.spdx_license_identifier == "MIT"
    assert result.copyright_text is None
    assert not result.file_contributors


def test_parse_file_header_no_header_at_all() -> None:
    """Plain code with no header comments returns None."""
    data = b"def foo():\n    return 1\n"
    assert parse_file_header(data) is None


def test_parse_file_header_binary_file_skipped() -> None:
    """Binary content (containing a null byte) is silently skipped, no
    exception raised."""
    data = b"\x89PNG\r\n\x1a\n" + b"\x00\x01\x02\x03" * 50
    assert parse_file_header(data) is None


def test_parse_file_header_scan_bounded_by_byte_limit() -> None:
    """A tag placed just past the byte-scan cutoff is not found."""
    padding = b"# padding line to burn bytes\n" * 200  # well over 4096 bytes
    assert len(padding) > 4096
    data = padding + b"# SPDX-License-Identifier: MIT\n"
    result = parse_file_header(data)
    assert result is None


def test_parse_file_header_scan_bounded_by_line_limit() -> None:
    """A tag placed on line 31+ (within the first 4KB) is not found."""
    padding = b"".join(f"# filler line {i}\n".encode() for i in range(30))
    data = padding + b"# SPDX-License-Identifier: MIT\n"
    assert len(data) < 4096
    result = parse_file_header(data)
    assert result is None


# ---------------------------------------------------------------------------
# guess_content_type
# ---------------------------------------------------------------------------


def test_guess_content_type_resolves_via_magika() -> None:
    """magika resolves a real MIME type for confidently-classifiable
    content, when installed."""
    pytest.importorskip("magika")
    data = b"import os\nprint(os.getcwd())\n" * 5
    mime_type, method = guess_content_type(data, "example.py")
    assert method == "magika"
    assert mime_type
    assert "/" in mime_type


def test_guess_content_type_falls_back_to_extension_when_magika_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When magika isn't importable, the stdlib filename-extension guess
    is used instead -- default method="auto"."""
    monkeypatch.setitem(sys.modules, "magika", None)
    mime_type, method = guess_content_type(b"whatever bytes", "example.py")
    assert method == "extension_guess"
    assert mime_type == "text/x-python"


def test_guess_content_type_returns_none_when_neither_resolves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unrecognized extension with magika unavailable resolves nothing."""
    monkeypatch.setitem(sys.modules, "magika", None)
    mime_type, method = guess_content_type(b"whatever bytes", "mystery.xyzzy123")
    assert (mime_type, method) == (None, None)


def test_guess_content_type_method_extension_skips_magika_even_when_installed() -> None:
    """method='extension' never attempts magika, even when it's importable."""
    pytest.importorskip("magika")
    data = b"import os\nprint(os.getcwd())\n" * 5
    mime_type, method = guess_content_type(data, "example.py", method="extension")
    assert method == "extension_guess"
    assert mime_type == "text/x-python"


def test_guess_content_type_method_magika_same_as_auto_when_available() -> None:
    """method='magika' behaves identically to 'auto' on a per-file basis
    when the package is installed -- the difference is enforced
    separately, up front, by require_magika_available()."""
    pytest.importorskip("magika")
    data = b"import os\nprint(os.getcwd())\n" * 5
    auto_result = guess_content_type(data, "example.py", method="auto")
    magika_result = guess_content_type(data, "example.py", method="magika")
    assert auto_result == magika_result == (auto_result[0], "magika")


def test_guess_content_type_method_magika_falls_back_when_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """method='magika' still falls back to the extension guess per-file
    when magika isn't importable -- require_magika_available() is the
    thing that turns this into a hard error, not guess_content_type()
    itself."""
    monkeypatch.setitem(sys.modules, "magika", None)
    mime_type, method = guess_content_type(
        b"whatever bytes", "example.py", method="magika"
    )
    assert method == "extension_guess"
    assert mime_type == "text/x-python"


# ---------------------------------------------------------------------------
# require_magika_available
# ---------------------------------------------------------------------------


def test_require_magika_available_no_op_when_installed() -> None:
    pytest.importorskip("magika")
    require_magika_available()  # must not raise


def test_require_magika_available_raises_when_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "magika", None)
    with pytest.raises(RuntimeError, match="content-type-method 'magika'"):
        require_magika_available()


# ---------------------------------------------------------------------------
# resolve_content_type_override
# ---------------------------------------------------------------------------


def test_resolve_content_type_override_simple_extension_match() -> None:
    """A bare '*.ext' pattern matches a file with that extension."""
    overrides = (ContentTypeOverride(pattern="*.woff2", content_type="font/woff2"),)
    result = resolve_content_type_override("assets/fonts/icons.woff2", overrides)
    assert result == overrides[0]


def test_resolve_content_type_override_directory_scoped_match_is_recursive() -> None:
    """'*' matches '/' too, so 'vendor/*' matches nested paths, not just
    direct children -- the intended "everything under this directory"
    shortcut, not gitignore-style directory-boundary matching."""
    overrides = (
        ContentTypeOverride(
            pattern="vendor/*", content_type="application/octet-stream"
        ),
    )
    result = resolve_content_type_override("vendor/pkg/deep/lib.bin", overrides)
    assert result == overrides[0]


def test_resolve_content_type_override_first_match_wins() -> None:
    """When multiple patterns match, the first one in configuration order wins."""
    overrides = (
        ContentTypeOverride(
            pattern="vendor/*", content_type="application/octet-stream"
        ),
        ContentTypeOverride(pattern="*.bin", content_type="application/x-binary"),
    )
    result = resolve_content_type_override("vendor/lib.bin", overrides)
    assert result is not None
    assert result.content_type == "application/octet-stream"


def test_resolve_content_type_override_no_match_returns_none() -> None:
    """A file matching no configured pattern resolves to None."""
    overrides = (ContentTypeOverride(pattern="*.woff2", content_type="font/woff2"),)
    assert resolve_content_type_override("src/main.py", overrides) is None


def test_resolve_content_type_override_empty_overrides_returns_none() -> None:
    """No overrides configured at all: always None."""
    assert resolve_content_type_override("src/main.py", ()) is None


def test_resolve_content_type_override_is_case_sensitive() -> None:
    """Matching uses fnmatch.fnmatchcase, not fnmatch.fnmatch -- the same
    pattern must behave identically regardless of host-OS case-folding, so
    a differently-cased path must not match."""
    overrides = (ContentTypeOverride(pattern="*.PNG", content_type="image/png"),)
    assert resolve_content_type_override("assets/logo.png", overrides) is None
