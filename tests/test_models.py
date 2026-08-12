# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for SPDX 3 core models."""

import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from hatchling.builders.wheel import WheelBuilder

from pitloom.core.content_type_config import ContentTypeOverride
from pitloom.core.models import (
    _clear_doc_counters,
    _normalize_dep,
    compute_doc_uuid,
    generate_spdx_id,
    get_wheel_files,
)
from pitloom.extract._file_headers import _get_magika


def test_normalize_dep_pep503() -> None:
    """PEP 503 name normalization leaves version/marker portion untouched."""
    assert _normalize_dep("Foo_Bar>=1.0") == "foo-bar>=1.0"
    assert _normalize_dep("PyProject.Metadata") == "pyproject-metadata"
    assert _normalize_dep("hatchling>=1.31.0") == "hatchling>=1.31.0"
    assert _normalize_dep("  tomli>=2.0; python_version<'3.11'  ") == (
        "tomli>=2.0; python_version<'3.11'"
    )
    assert _normalize_dep("My---Pkg") == "my-pkg"


def test_compute_doc_uuid_deterministic() -> None:
    """Same inputs always produce the same UUID."""
    uuid1 = compute_doc_uuid("mypkg", "1.0.0", ["requests>=2.0", "click>=8.0"])
    uuid2 = compute_doc_uuid("mypkg", "1.0.0", ["requests>=2.0", "click>=8.0"])
    assert uuid1 == uuid2


def test_compute_doc_uuid_dep_normalization() -> None:
    """Dependency name normalization is applied before hashing."""
    uuid_canonical = compute_doc_uuid("mypkg", "1.0", ["my-lib>=1.0"])
    uuid_underscore = compute_doc_uuid("mypkg", "1.0", ["my_lib>=1.0"])
    uuid_dot = compute_doc_uuid("mypkg", "1.0", ["my.lib>=1.0"])
    assert uuid_canonical == uuid_underscore == uuid_dot


def test_compute_doc_uuid_dep_order_independent() -> None:
    """Dependency list order does not affect the UUID."""
    uuid_a = compute_doc_uuid("mypkg", "1.0", ["alpha>=1", "beta>=2"])
    uuid_b = compute_doc_uuid("mypkg", "1.0", ["beta>=2", "alpha>=1"])
    assert uuid_a == uuid_b


def test_compute_doc_uuid_differs_on_change() -> None:
    """Different name, version, deps, or merkle_root produce different UUIDs."""
    base = compute_doc_uuid("mypkg", "1.0", ["dep>=1"])
    assert base != compute_doc_uuid("other", "1.0", ["dep>=1"])
    assert base != compute_doc_uuid("mypkg", "2.0", ["dep>=1"])
    assert base != compute_doc_uuid("mypkg", "1.0", ["dep>=2"])
    assert base != compute_doc_uuid("mypkg", "1.0", ["dep>=1"], merkle_root="abc123")


def test_clear_doc_counters_resets_sequence() -> None:
    """Element IDs must restart from 1 after _clear_doc_counters()."""
    doc_uuid = compute_doc_uuid("resetpkg", "1.0", [])
    _clear_doc_counters(doc_uuid)
    id1 = generate_spdx_id("Package", doc_name="resetpkg", doc_uuid=doc_uuid)
    _clear_doc_counters(doc_uuid)
    id2 = generate_spdx_id("Package", doc_name="resetpkg", doc_uuid=doc_uuid)
    assert id1 == id2
    assert id1.endswith("#Package-1")


def test_compute_doc_uuid_field_boundary_no_collision() -> None:
    """Input combinations that would collide under a naive ':' separator must not.

    With ':' as separator, name="a:b" + version="c" + deps=[] and
    name="a" + version="b:c" + deps=[] both produce the seed "a:b:c:".
    The NUL separator is immune because PEP 508 names, PEP 440 versions, and
    SHA-256 hex digests cannot contain \\x00.
    """
    # Same number of ':' characters -- would collide with ':' separator
    uuid_split_in_name = compute_doc_uuid("my-pkg", "1.0", ["dep-a>=1", "dep-b>=2"])
    uuid_split_in_version = compute_doc_uuid("my-pkg", "2.0", ["dep-a>=1"])
    uuid_no_deps = compute_doc_uuid("my-pkg", "1.0", [])
    assert len({uuid_split_in_name, uuid_split_in_version, uuid_no_deps}) == 3


def test_generate_spdx_id() -> None:
    """Test SPDX ID generation."""
    person_id = generate_spdx_id("Person")
    assert person_id.startswith("https://spdx.org/spdxdocs/pitloom-")
    assert "#Person-" in person_id

    package_id = generate_spdx_id("Package")
    assert package_id.startswith("https://spdx.org/spdxdocs/pitloom-")
    assert "#Package-" in package_id

    doc_id = generate_spdx_id("SpdxDocument")
    assert doc_id.startswith("https://spdx.org/spdxdocs/pitloom-")
    assert "#" not in doc_id


# pylint: disable-next=too-few-public-methods
class _FakeIncludedFile:
    """Minimal stand-in for ``hatchling.builders.plugin.interface.IncludedFile``."""

    def __init__(self, path: str, distribution_path: str):
        self.path = path
        self.relative_path = distribution_path
        self.distribution_path = distribution_path


def test_get_wheel_files_normalizes_windows_style_distribution_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: Hatchling builds ``distribution_path`` with
    ``os.path.join``, which uses backslashes on Windows -- unlike a
    wheel's actual internal zip-entry paths, which the ZIP format itself
    requires to be forward-slash-separated regardless of host OS. Left
    un-normalized, the Merkle root (and the ``doc_uuid`` built from it)
    would differ by build platform for byte-identical source content,
    since both the sort key and the tree-combination input are exactly
    this string.

    Uses two files, ``pkg/zoo.py`` and ``pkg0/a.py``, deliberately chosen
    so their relative sort order flips depending on the separator: ``/``
    (0x2F) sorts before ``0`` (0x30), so ``pkg/zoo.py`` sorts first in
    POSIX form -- but ``\\`` (0x5C) sorts *after* ``0``, so
    ``pkg\\zoo.py`` would sort *second* in un-normalized Windows form.
    With only one file (or a pair whose order doesn't happen to flip),
    the Merkle root would trivially match either way and this test
    wouldn't actually prove anything.
    """
    (tmp_path / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["hatchling"]\n'
        'build-backend = "hatchling.build"\n\n'
        '[project]\nname = "pkg"\nversion = "1.0.0"\n',
        encoding="utf-8",
    )
    pkg_dir = tmp_path / "pkg"
    pkg_dir.mkdir()
    zoo_file = pkg_dir / "zoo.py"
    zoo_file.write_text("zoo = 1\n", encoding="utf-8")
    pkg0_dir = tmp_path / "pkg0"
    pkg0_dir.mkdir()
    a_file = pkg0_dir / "a.py"
    a_file.write_text("a = 1\n", encoding="utf-8")

    def _make_fake_recurse(
        sep: str,
    ) -> Callable[[WheelBuilder], Iterator[_FakeIncludedFile]]:
        def _fake_recurse(_self: WheelBuilder) -> Iterator[_FakeIncludedFile]:
            yield _FakeIncludedFile(str(zoo_file), f"pkg{sep}zoo.py")
            yield _FakeIncludedFile(str(a_file), f"pkg0{sep}a.py")

        return _fake_recurse

    monkeypatch.setattr(WheelBuilder, "recurse_included_files", _make_fake_recurse("/"))
    posix_root, posix_files = get_wheel_files(tmp_path)

    monkeypatch.setattr(
        WheelBuilder, "recurse_included_files", _make_fake_recurse("\\")
    )
    windows_root, windows_files = get_wheel_files(tmp_path)

    assert posix_root is not None
    assert posix_root == windows_root, (
        "Merkle root must not depend on the build platform's path separator"
    )
    assert [f.distribution_path for f in posix_files] == ["pkg/zoo.py", "pkg0/a.py"]
    assert [f.distribution_path for f in windows_files] == ["pkg/zoo.py", "pkg0/a.py"]


# ---------------------------------------------------------------------------
# get_wheel_files: scan_file_headers / detect_content_type
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_magika_cache() -> None:
    """``_get_magika()`` caches its instance for process lifetime; clear it
    around every test in this module so a test that runs the real
    ``guess_content_type()`` (caching a real instance when magika is
    installed) can't leak that cache into a later test that monkeypatches
    ``sys.modules["magika"] = None`` to simulate its absence."""
    _get_magika.cache_clear()


def _make_header_project(tmp_path: Path) -> tuple[Path, Path]:
    """Build a minimal project with one SPDX-tagged file and one plain file.

    Returns (tagged_file, plain_file).
    """
    (tmp_path / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["hatchling"]\n'
        'build-backend = "hatchling.build"\n\n'
        '[project]\nname = "pkg"\nversion = "1.0.0"\n',
        encoding="utf-8",
    )
    pkg_dir = tmp_path / "pkg"
    pkg_dir.mkdir()
    tagged_file = pkg_dir / "tagged.py"
    tagged_file.write_text(
        "# SPDX-FileCopyrightText: 2026 Test Author\n"
        "# SPDX-License-Identifier: MIT\n"
        "value = 1\n",
        encoding="utf-8",
    )
    plain_file = pkg_dir / "plain.py"
    plain_file.write_text("value = 2\n", encoding="utf-8")
    return tagged_file, plain_file


def _patch_recurse(
    monkeypatch: pytest.MonkeyPatch, tagged_file: Path, plain_file: Path
) -> None:
    def _fake_recurse(_self: WheelBuilder) -> Iterator[_FakeIncludedFile]:
        yield _FakeIncludedFile(str(tagged_file), "pkg/tagged.py")
        yield _FakeIncludedFile(str(plain_file), "pkg/plain.py")

    monkeypatch.setattr(WheelBuilder, "recurse_included_files", _fake_recurse)


def test_get_wheel_files_scan_file_headers_disabled_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With both new params at their own default (False), no header
    parsing or content-type detection happens -- new ProjectFile fields
    stay empty even for a file that carries SPDX tags."""
    tagged_file, plain_file = _make_header_project(tmp_path)
    _patch_recurse(monkeypatch, tagged_file, plain_file)

    calls: list[str] = []

    def _spy_parse(data: bytes) -> None:
        del data
        calls.append("parse_file_header")

    def _spy_guess(data: bytes, filename: str, method: str) -> tuple[None, None]:
        del data, filename, method
        calls.append("guess_content_type")
        return None, None

    monkeypatch.setattr("pitloom.extract._file_headers.parse_file_header", _spy_parse)
    monkeypatch.setattr("pitloom.extract._file_headers.guess_content_type", _spy_guess)

    _root, files = get_wheel_files(tmp_path)

    assert not calls
    tagged = next(f for f in files if f.distribution_path == "pkg/tagged.py")
    assert tagged.copyright_text is None
    assert tagged.file_type is None
    assert tagged.spdx_license_identifier is None
    assert tagged.content_type is None
    assert tagged.content_type_method is None


def test_get_wheel_files_scan_file_headers_enabled_content_type_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """scan_file_headers=True, detect_content_type=False: tag fields are
    populated for the tagged file; content_type stays empty and
    guess_content_type is never called."""
    tagged_file, plain_file = _make_header_project(tmp_path)
    _patch_recurse(monkeypatch, tagged_file, plain_file)

    content_type_calls: list[str] = []

    def _spy_guess(data: bytes, filename: str, method: str) -> tuple[None, None]:
        del data, method
        content_type_calls.append(filename)
        return None, None

    monkeypatch.setattr("pitloom.extract._file_headers.guess_content_type", _spy_guess)

    _root, files = get_wheel_files(tmp_path, scan_file_headers=True)

    assert not content_type_calls
    tagged = next(f for f in files if f.distribution_path == "pkg/tagged.py")
    assert tagged.copyright_text == "2026 Test Author"
    assert tagged.copyright_source == "spdx_tag"
    assert tagged.spdx_license_identifier == "MIT"
    assert tagged.content_type is None
    plain = next(f for f in files if f.distribution_path == "pkg/plain.py")
    assert plain.copyright_text is None


def test_get_wheel_files_detect_content_type_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both params True: content_type is resolved for every file,
    regardless of whether it has any header tag at all."""
    tagged_file, plain_file = _make_header_project(tmp_path)
    _patch_recurse(monkeypatch, tagged_file, plain_file)

    _root, files = get_wheel_files(
        tmp_path, scan_file_headers=True, detect_content_type=True
    )

    for project_file in files:
        assert project_file.content_type is not None
        assert project_file.content_type_method in (
            "magika",
            "extension_guess",
        )


def test_get_wheel_files_merkle_root_identical_across_flag_combinations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Merkle root only ever consumes file-content hashes -- it must
    be identical for the same files regardless of scan_file_headers/
    detect_content_type, since neither flag changes what bytes are
    hashed."""
    tagged_file, plain_file = _make_header_project(tmp_path)

    _patch_recurse(monkeypatch, tagged_file, plain_file)
    root_off, _ = get_wheel_files(tmp_path)

    _patch_recurse(monkeypatch, tagged_file, plain_file)
    root_headers, _ = get_wheel_files(tmp_path, scan_file_headers=True)

    _patch_recurse(monkeypatch, tagged_file, plain_file)
    root_both, _ = get_wheel_files(
        tmp_path, scan_file_headers=True, detect_content_type=True
    )

    assert root_off is not None
    assert root_off == root_headers == root_both


def test_get_wheel_files_content_type_override_shortcuts_detection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With detect_content_type=True and a matching override, the matched
    file's content_type comes from the override -- guess_content_type is
    never called for it -- while a non-matching file in the same run
    still goes through the normal detection path."""
    tagged_file, plain_file = _make_header_project(tmp_path)
    _patch_recurse(monkeypatch, tagged_file, plain_file)

    guess_calls: list[str] = []

    def _spy_guess(data: bytes, filename: str, method: str) -> tuple[str, str]:
        del data, method
        guess_calls.append(filename)
        return "text/x-python", "extension_guess"

    monkeypatch.setattr("pitloom.extract._file_headers.guess_content_type", _spy_guess)

    overrides = (
        ContentTypeOverride(pattern="pkg/tagged.py", content_type="text/special"),
    )
    _root, files = get_wheel_files(
        tmp_path, detect_content_type=True, content_type_overrides=overrides
    )

    assert guess_calls == ["plain.py"]
    tagged = next(f for f in files if f.distribution_path == "pkg/tagged.py")
    assert tagged.content_type == "text/special"
    assert tagged.content_type_method == "config_override"
    plain = next(f for f in files if f.distribution_path == "pkg/plain.py")
    assert plain.content_type == "text/x-python"
    assert plain.content_type_method == "extension_guess"


def test_get_wheel_files_content_type_override_inert_when_detection_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With detect_content_type=False, overrides never fire -- no file
    gets a content_type at all, override configured or not, proving the
    gate still governs the whole feature rather than being bypassed."""
    tagged_file, plain_file = _make_header_project(tmp_path)
    _patch_recurse(monkeypatch, tagged_file, plain_file)

    overrides = (
        ContentTypeOverride(pattern="pkg/tagged.py", content_type="text/special"),
    )
    _root, files = get_wheel_files(tmp_path, content_type_overrides=overrides)

    for project_file in files:
        assert project_file.content_type is None
        assert project_file.content_type_method is None


# ---------------------------------------------------------------------------
# get_wheel_files: content_type_method (the "two gates" combinatorial surface)
# ---------------------------------------------------------------------------


def test_get_wheel_files_content_type_method_defaults_to_auto(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No content_type_method passed: 'auto' reaches guess_content_type."""
    tagged_file, plain_file = _make_header_project(tmp_path)
    _patch_recurse(monkeypatch, tagged_file, plain_file)

    seen_methods: list[str] = []

    def _spy_guess(data: bytes, filename: str, method: str) -> tuple[str, str]:
        del data, filename
        seen_methods.append(method)
        return "text/x-python", "extension_guess"

    monkeypatch.setattr("pitloom.extract._file_headers.guess_content_type", _spy_guess)

    get_wheel_files(tmp_path, detect_content_type=True)

    assert seen_methods == ["auto", "auto"]


@pytest.mark.parametrize("method", ["auto", "extension"])
def test_get_wheel_files_content_type_method_plumbed_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, method: str
) -> None:
    """content_type_method is passed through to every guess_content_type
    call verbatim (magika is covered separately below, since it also
    triggers the upfront availability preflight)."""
    tagged_file, plain_file = _make_header_project(tmp_path)
    _patch_recurse(monkeypatch, tagged_file, plain_file)

    seen_methods: list[str] = []

    def _spy_guess(data: bytes, filename: str, seen_method: str) -> tuple[str, str]:
        del data, filename
        seen_methods.append(seen_method)
        return "text/x-python", "extension_guess"

    monkeypatch.setattr("pitloom.extract._file_headers.guess_content_type", _spy_guess)

    get_wheel_files(tmp_path, detect_content_type=True, content_type_method=method)

    assert seen_methods == [method, method]


def test_get_wheel_files_content_type_method_magika_available_plumbed_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """content_type_method='magika' with magika importable: no error, and
    'magika' reaches every guess_content_type call."""
    pytest.importorskip("magika")
    tagged_file, plain_file = _make_header_project(tmp_path)
    _patch_recurse(monkeypatch, tagged_file, plain_file)

    seen_methods: list[str] = []

    def _spy_guess(data: bytes, filename: str, method: str) -> tuple[str, str]:
        del data, filename
        seen_methods.append(method)
        return "text/x-python", "magika"

    monkeypatch.setattr("pitloom.extract._file_headers.guess_content_type", _spy_guess)

    get_wheel_files(tmp_path, detect_content_type=True, content_type_method="magika")

    assert seen_methods == ["magika", "magika"]


def test_get_wheel_files_content_type_method_magika_missing_raises_before_any_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """content_type_method='magika' with the package unavailable raises
    RuntimeError up front -- before recursing into any file at all, not
    partway through a scan."""
    tagged_file, plain_file = _make_header_project(tmp_path)
    _patch_recurse(monkeypatch, tagged_file, plain_file)
    monkeypatch.setitem(sys.modules, "magika", None)

    recurse_calls: list[str] = []

    def _spy_guess(data: bytes, filename: str, method: str) -> tuple[str, str]:
        del data, method
        recurse_calls.append(filename)
        return "text/x-python", "extension_guess"

    monkeypatch.setattr("pitloom.extract._file_headers.guess_content_type", _spy_guess)

    with pytest.raises(RuntimeError, match="content-type-method 'magika'"):
        get_wheel_files(
            tmp_path, detect_content_type=True, content_type_method="magika"
        )

    assert not recurse_calls


def test_get_wheel_files_content_type_method_magika_missing_inert_when_detection_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """content_type_method='magika' with the package unavailable does NOT
    raise when detect_content_type=False -- the preflight check is itself
    gated by detection being on, same as everything else content-type."""
    tagged_file, plain_file = _make_header_project(tmp_path)
    _patch_recurse(monkeypatch, tagged_file, plain_file)
    monkeypatch.setitem(sys.modules, "magika", None)

    _root, files = get_wheel_files(tmp_path, content_type_method="magika")

    for project_file in files:
        assert project_file.content_type is None


@pytest.mark.parametrize("scan_file_headers", [False, True])
def test_get_wheel_files_content_type_independent_of_file_header_scanning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scan_file_headers: bool
) -> None:
    """A file with no SPDX header at all (the AI-model-binary case) still
    gets a content_type when detection is on, regardless of whether
    file-header scanning is on or off -- the two gates are independent."""
    tagged_file, plain_file = _make_header_project(tmp_path)
    _patch_recurse(monkeypatch, tagged_file, plain_file)

    _root, files = get_wheel_files(
        tmp_path,
        scan_file_headers=scan_file_headers,
        detect_content_type=True,
        content_type_method="extension",
    )

    plain = next(f for f in files if f.distribution_path == "pkg/plain.py")
    assert plain.copyright_text is None  # no header, regardless of the flag
    assert plain.content_type == "text/x-python"
    assert plain.content_type_method == "extension_guess"
