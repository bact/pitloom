# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Drift guard on the docs and the skills: a backticked quote that holds a
catalogued family's marker text is a piece of one of its patterns, at a level
and with a code the entry has. Wording changes in the catalogue fail here
until the quote follows.

A quote may leave text out (``...``), name a value (``<path>``, ``%s``,
``(N files)``, ``byte(s)``, ``N-byte``) or give one (``'m.gguf'``,
``3 bytes``), start with ``LEVEL: `` and end with `` [code]``. A value given
has its field's shape; a free one (a file name) never holds the family's
marker, so the marker is the catalogue's wording, not a value.

See also: tests/messages/test_drift_sources.py, test_drift_records.py.
"""

from __future__ import annotations

import re

import pytest

from pitloom.messages import MESSAGES
from tests._docs_scan import CLI_DOC_FILES, read
from tests._message_drift import quote_matches, relative

#: The texts that mark a quote as saying a family's message: one, or one per
#: line for a family whose lines share no core.
_MARKERS: dict[str, tuple[str, ...]] = {
    "card-malformed": ("frontmatter is not valid YAML",),
    "config-unsafe": ("[tool.pitloom] settings are ignored",),
    "digest-invalid": ("declared by ",),
    "dir-unlistable": ("could not list ",),
    "download-network-failed": ("URL=",),
    "download-timeout": ("no complete answer within ",),
    "field-not-recordable": ("no SPDX 3.0.1 property",),
    "file-ambiguous": (
        "match this environment; using ",
        " sdists; using ",
        "loom generate reads the wheel",
        "generate() reads the wheel",
    ),
    "file-unreadable": ("could not read ",),
    "hyperparameter-conflict": ("replaced by the parameter count",),
    "input-not-found": ("Model file not found", "in the repository at that branch"),
    "json-malformed": ("not valid JSON for ",),
    "lfs-pointer": ("Git LFS pointer",),
    "lfs-pointer-malformed": ("Git LFS pointer",),
    "library-missing": ("required library not installed",),
    "library-unusable": ("required library failed to import",),
    "model-field-conflict": ("the length of array ", "appear more than once"),
    "model-field-unreadable": (
        "Failed to read fastText model",
        "fickling failed to parse pickle",
        "fickling parsed pickle but",
        "Failed to inspect ",
        "Failed to parse PT2 ",
        "Failed to read PT2 ",
        "attribute cannot be read",
        "kept as properties.model_config_raw",
        "the fields read before it are kept",
        "reading stopped there",
    ),
    "model-ambiguous": ("several AI model files",),
    "model-unreadable": ("failed to extract metadata",),
    "model-wrong-format": ("header is not ",),
    "over-cap": (" cap;",),
    "parameter-count-invalid": ("parameter count not recorded",),
    "project-not-found": ("No pyproject.toml, setup.cfg, or setup.py found",),
    "project-or-model-not-found": ("no Python project (pyproject.toml",),
    "pypi-response-invalid": (
        "declares no SHA-256 digest",
        "PyPI answered for project ",
        "PyPI JSON API answer has no valid ",
    ),
    "pypi-url-invalid": (
        "not a PyPI project or release page",
        "PyPI is read over https only",
        "holds user information",
        "only pypi.org is read",
        "is PyPI's old address",
        "a file link is not read yet",
        "is not a valid project name",
        "is not a PEP 440 version",
    ),
    "reader-unsafe": ("pass --trust-model-files", "run on a downloaded file"),
    "release-file-not-found": (
        "the release has no wheel",
        "no wheel matches this Python",
        "the release has no sdist",
    ),
    "release-not-found": (
        "no such project on PyPI",
        "no such release on PyPI",
        "no release has a wheel or sdist",
    ),
    "release-unpinned": ("no version given",),
    "query-no-effect": ("the query and fragment have no effect",),
    "release-unusable": ("the file is yanked",),
    "target-ambiguous": (
        "not an AI model file; reading its folder",
        "no Python project; reading this AI model file",
        "the one AI model file; reading it",
    ),
    "pypi-url-unusable": (
        "--embed writes into a wheel file",
        "a PyPI page is not a model",
        "a PyPI page is not a Git repository",
    ),
    "temp-dir-unusable": ("could not be saved in the temporary directory",),
    "text-malformed": ("lone surrogates written",),
    "url-moved": ("; followed",),
    "url-unsafe": ("redirects to ", "; not fetched"),
    "usage-unparseable": ("could not parse as Python ",),
    "usage-unusable": ("not scanned for usage",),
}

#: Quotes of a tool's own lines, which no pattern here covers: (file, quote).
#: Shrink only.
_EXTERNAL: frozenset[tuple[str, str]] = frozenset()

_SPAN = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)", re.DOTALL)
_FENCE = re.compile(r"^[ \t]*```.*?^[ \t]*```", re.DOTALL | re.MULTILINE)


def _quotes() -> list[tuple[str, tuple[str, ...], str]]:
    """(file, families, quote) for each inline code span, wrapped lines
    joined, that holds a family's marker: the families whose marker it
    holds, one of which it must say."""
    found = []
    for path in CLI_DOC_FILES:
        text = _FENCE.sub("", read(path))
        for span in _SPAN.finditer(text):
            # A table cell escapes a pipe, in a code span too (GFM).
            quote = " ".join(span.group(2).replace("\\|", "|").split())
            families = tuple(
                f for f, markers in _MARKERS.items() if any(m in quote for m in markers)
            )
            if families and (relative(path), quote) not in _EXTERNAL:
                found.append((relative(path), families, quote))
    return found


def test_every_family_has_a_marker() -> None:
    assert {m.family for m in MESSAGES.values()} <= set(_MARKERS)


_QUOTES = _quotes()


def test_the_scan_found_quotes() -> None:
    """The model-stub table in ``model-stub-diagnosis.md`` is generated, so it
    is exact by construction (tests/messages/test_generated_reference.py)."""
    files = {file for file, _, _ in _QUOTES}
    assert {
        "docs/ai-model-scan-limits.md",
        "skills/sbom-enrich/references/deterministic-pass.md",
        "skills/sbom-generate/references/git-url.md",
        "skills/sbom-generate/references/known-limitations.md",
    } <= files
    assert {f for _, families, _ in _QUOTES for f in families} == set(_MARKERS)


@pytest.mark.parametrize(
    ("file", "families", "quote"),
    _QUOTES,
    ids=[f"{file}:{quote[:40]}" for file, _, quote in _QUOTES],
)
def test_a_quote_is_a_piece_of_the_catalogue(
    file: str, families: tuple[str, ...], quote: str
) -> None:
    assert any(
        quote_matches(quote, f, marker)
        for f in families
        for marker in _MARKERS[f]
        if marker in quote
    ), f"{file}: {quote!r}"


@pytest.mark.parametrize(
    ("quote", "expected"),
    [
        ("WARNING: ... Git LFS pointer, content not read ... [lfs-pointer]", True),
        ("Git LFS pointer, content not read", True),
        ("WARNING: FILE=<first>: Git LFS pointer, content not read (N files);", True),
        (
            "ERROR: ... header is a Git LFS pointer, content not pulled "
            "(oid sha256:<oid>, size <N> byte(s)); run 'git lfs pull'",
            True,
        ),
        ("Git LFS pointer, content not read [lfs-pointer/shipped]", False),
        ("INFO: Git LFS pointer shipped; the build did not pull LFS content", False),
        ("WARNING: Git LFS pointer, content unread", False),
        ("Git LFS pointer is skipped", False),
        # values given as themselves, or as the reference shows them
        (
            "ERROR: 'm.gguf': header is a Git LFS pointer, content not pulled "
            f"(oid sha256:{'0f' * 32}, size 3 bytes); run 'git lfs pull'",
            True,
        ),
        ("ERROR: '<path>': header is a Git LFS pointer, content not pulled", True),
        ("WARNING: FILE=m/a.bin: Git LFS pointer, content not read (2 files);", True),
        # a value without its field's shape, or one holding the marker
        ("ERROR: m.gguf: header is a Git LFS pointer, content not pulled", False),
        ("header is a Git LFS pointer, content not pulled (oid sha256:zz,", False),
        (
            "Git LFS pointer, content not pulled (oid sha256:<oid>, size 3x bytes)",
            False,
        ),
        ("WARNING: FILE=Git LFS pointer, content not read", False),
    ],
    ids=lambda v: str(v)[:24],
)
def test_the_matcher_reads_elisions_and_checks_level_code_and_wording(
    quote: str, expected: bool
) -> None:
    assert quote_matches(quote, "lfs-pointer", *_MARKERS["lfs-pointer"]) is expected


@pytest.mark.parametrize(
    ("quote", "expected"),
    [
        ("... larger than the 10000-byte .npy-header cap; metadata not read", True),
        (
            "WARNING: FILE=<wheel>: larger than the N-byte per-wheel model-scan budget",
            True,
        ),
        ("WARNING: ... model-scan budget cap; ...", True),
        (
            "WARNING: FORMAT=<fmt> FILE=<path>:<member>: larger than the "
            "8388608-byte archive-member cap; metadata not read",
            True,
        ),
        ("FILE=<path>: larger than the 10-byte usage-scan limit cap; skipped", True),
        (
            "ERROR: config file '<path>': larger than the <limit>-byte config-member "
            "cap; not read [over-cap]",
            True,
        ),
        # the wording, a value's shape, the level or the code differs
        ("WARNING: FILE=<path>: larger than 10 bytes cap; skipped", False),
        ("WARNING: FILE=<path>: over the 10-byte usage-scan cap; skipped", False),
        ("FILE=<path>: larger than the 10-megabyte usage-scan cap; skipped", False),
        ("FILE=<path>: larger than the 10-byte a b c d cap; skipped", False),
        ("ERROR: FILE=<path>: larger than the 10-byte usage-scan cap; skipped", False),
        ("INFO: FILE=<path>: larger than the 10-byte usage-scan cap; skipped", False),
        ("FILE=<p>: larger than the 10-byte usage-scan cap; x [lfs-pointer]", False),
    ],
    ids=lambda v: str(v)[:24],
)
def test_the_matcher_reads_the_values_of_a_cap_line(quote: str, expected: bool) -> None:
    assert quote_matches(quote, "over-cap", *_MARKERS["over-cap"]) is expected
