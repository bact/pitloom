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
    "build-code-unsafe": ("--allow-build runs a PEP 517 build",),
    "build-failed": (
        "the build exited with code",
        "no Python interpreter to run PyPA build with",
        "the build wrote ",
        "the built wheel holds no file outside",
        "the build could not run or its wheel",
    ),
    "build-processes-unsafe": ("the build left processes running",),
    "build-timeout": ("the build timed out after",),
    "card-malformed": ("frontmatter is not valid YAML",),
    "config-invalid": (": must be ",),
    "config-malformed": ("not valid TOML; ", "not valid INI"),
    "config-moved": (": moved to ",),
    "config-unknown-key": (
        "unknown key",
        "only enabled and Hatchling's own hook keys",
    ),
    "config-unsafe": (
        "[tool.pitloom] settings are ignored",
        "build-time code of the downloaded",
    ),
    "credentials-unsafe": (
        "are not sent to git",
        "credentials are sent in clear",
        "an ID registry key is stored as written",
        "an ID registry namespace is stored as written",
        "so the element is skipped",
        "cannot be taken out of the git command line",
        "hold credentials; the SBOM is refused",
        "or accept this value ",
        "accepts; the SBOM states it as written",
        "an ssh user name; the SBOM states it as written",
        "is not loaded; remove the entry",
        "is loaded as it is; remove the entry",
        "the ID registry stores the key as written",
        "the SBOM states it as written; remove it from the source",
    ),
    "datetime-unpinned": ("come from the clock; set ",),
    "dependency-name-ambiguous": ("a direct reference; not looked up",),
    "dependency-pin-conflict": (
        "exact pin disagree",
        "does not satisfy the declared",
    ),
    "digest-invalid": ("declared by ",),
    "dir-unlistable": ("could not list ",),
    "download-network-failed": ("URL=", "; nothing fetched"),
    "download-timeout": ("no complete answer within ", "did not finish within "),
    "dynamic-field-needs-build": (
        "not resolvable without running project code",
        "not resolved without PKG-INFO",
    ),
    "dynamic-field-unusable": (
        "dynamic version not resolved",
        "dynamic metadata not resolved",
    ),
    "extra-gate-ambiguous": ("needs extras ",),
    "extra-gate-unusable": ("cannot be isolated",),
    "field-not-recordable": ("no SPDX 3.0.1 property",),
    "file-ambiguous": (
        "match this environment; using ",
        " sdists; using ",
        "loom generate reads the wheel",
        "generate() reads the wheel",
    ),
    "file-discovery-conflict": ("map to wheel path",),
    "file-discovery-needs-build": (
        "not backend-aware",
        "config resolvable",
        "overrides the heuristic cannot see",
        "imperatively; file list",
        "[tool.flit.external-data] without",
    ),
    "file-discovery-unusable": (
        "file discovery failed",
        "failed introspection",
        "auto-discovery is ambiguous",
    ),
    "file-unreadable": ("could not read ", "outside the downloaded repository"),
    "file-unwritable": ("could not write ",),
    "git-filter-unusable": ("rejected the blob filter",),
    "git-link-unsafe": ("symbolic link(s) leading out of the repository",),
    "git-missing": ("git is not installed or not on PATH",),
    "git-redirect-unusable": ("could not be checked for a redirect",),
    "git-ref-not-found": ("no branch or tag ",),
    "git-repository-unusable": (
        "an empty repository (no commits)",
        "; nothing fetched",
    ),
    "git-url-invalid": (
        "only http and https URLs are fetched",
        "the port is not a number",
        "a path part decodes to ",
    ),
    "hf-url-invalid": ("not a valid Hugging Face URL",),
    "hub-response-invalid": ("the Hub's answer could not be read",),
    "hub-revision-unpinned": ("the Hub stated no revision",),
    "hyperparameter-conflict": ("replaced by the parameter count",),
    "index-path-no-effect": ("skipped directory name",),
    "input-not-found": (
        "Model file not found",
        "in the repository at that branch",
        "SBOM fragment not found",
        "no wheel file matches",
        "no JSON fragment file in",
        "<input> not found: ",
        "directory not found: ",
        "file not found: ",
        "archive not found: ",
        "path not found: ",
        "PATH not found: ",
    ),
    "installed-metadata-ambiguous": ("installed-metadata candidates",),
    "installed-metadata-unusable": (
        "not the project's; ignored",
        "declares no name",
    ),
    "interrupted": ("received SIGTERM", ": interrupted"),
    "json-malformed": ("not valid JSON for ",),
    "lfs-pointer": ("Git LFS pointer",),
    "lfs-pointer-malformed": ("Git LFS pointer",),
    "library-missing": ("required library not installed",),
    "library-unusable": ("required library failed to import",),
    "license-ambiguous": ("several licence classifiers",),
    "license-conflict": ("both state a licence",),
    "license-db-missing": ("licenseid database not found",),
    "license-db-unusable": ("licenseid database cannot be used",),
    "license-expression-invalid": (
        "not a valid SPDX license expression",
        "not read as an SPDX license expression",
    ),
    "license-expression-malformed": ("malformed SPDX license expression",),
    "license-relationship-invalid": (
        "a licence relationship goes to ",
        "a licence relationship starts at ",
        "left a licence relationship of the wrong type",
    ),
    "lock-entry-conflict": ("pinned to several versions",),
    "lock-entry-malformed": ("referenced but not in the lock",),
    "lock-entry-unusable": ("not a registry version",),
    "lock-file-conflict": ("two lock files hold resolved dependencies",),
    "lock-file-malformed": ("does not parse: ",),
    "lock-file-unusable": ("no entry for the project",),
    "lock-file-wrong-format": ("a major version Pitloom does not read",),
    "metadata-conflict": (
        "setup.py and setup.cfg disagree",
        "declared and installed metadata",
    ),
    "metadata-invalid": (
        "not valid [project] metadata",
        "has a number over ",
        "[project] has no name",
        "setup() keyword ",
        "is not a table with 'file'",
        "not supported for requirements",
        "listed by ",
    ),
    "metadata-malformed": (
        "not valid Python; ",
        "too deeply nested to parse",
    ),
    "metadata-no-effect": (
        "not read: Poetry reads [project]",
        "does not read them",
        "setuptools does not accept",
    ),
    "model-ambiguous": ("several AI model files", "could be AI models, none read"),
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
    "model-unreadable": ("failed to extract metadata",),
    "model-wrong-format": (
        "header is not ",
        "file is empty",
        "not an AI model file of a supported format",
    ),
    "offline-unusable": ("network access is forbidden",),
    "option-conflict": ("cannot be used when", "delete it to change the "),
    "option-invalid": (
        "unrecognized arguments",
        "build timeout must be",
        "is outside --project-dir",
        "not inside the project root",
    ),
    "option-missing": (
        "the following arguments are required",
        "no ID registry declared",
        "-o/--output is required",
    ),
    "option-no-effect": ("has no effect", "matches no URL of th"),
    "over-cap": (" cap;",),
    "parameter-count-invalid": ("parameter count not recorded",),
    "project-name-missing": (
        "no project name",
        "has a project name",
    ),
    "project-not-found": (
        "No pyproject.toml, setup.cfg, or setup.py found",
        "Python projects are in subfolders",
    ),
    "project-or-model-not-found": (
        "no Python project (pyproject.toml",
        "Python projects are in subfolders",
    ),
    "pypi-response-invalid": (
        "declares no SHA-256 digest",
        "PyPI answered for project ",
        "PyPI JSON API answer has no valid ",
    ),
    "pypi-url-invalid": (
        "not a PyPI project or release page",
        "PyPI is read over https only",
        "holds user information; a PyPI URL",
        "only pypi.org is read",
        "is PyPI's old address",
        "a file link is not read yet",
        "is not a valid project name",
        "is not a PEP 440 version",
    ),
    "pypi-url-unusable": (
        "--embed writes into a wheel file",
        "a PyPI page is not a model",
        "a PyPI page is not a Git repository",
    ),
    "query-no-effect": (
        "the query and fragment have no effect",
        "the version names no branch",
    ),
    "reader-unsafe": ("pass --trust-model-files", "run on a downloaded file"),
    "registry-conflict": (
        "is registered for both",
        "another run saved",
        "but it is read as",
        "its id is held under",
        "is held under another type",
        "inside the project's file set",
        "inside dataset directory",
    ),
    "registry-entry-missing": ("not found; minting a new spdxId",),
    "registry-file-missing": ("no file to save to",),
    "registry-hash-conflict": (
        "content changed for",
        "no longer matches",
        "no registry entry records its SHA-256",
        "content gate ",
    ),
    "registry-hash-missing": (
        "looked up ungated",
        "pin without SHA-256",
        "pinned without SHA-256",
        "pin now gated",
        "no content was hashed",
    ),
    "registry-identity-missing": (
        "package identity unknown",
        "stored without a version",
    ),
    "registry-key-ambiguous": (
        "once NFC-normalised",
        "more than one layout alias",
        "name held by several elements",
    ),
    "registry-key-moved": (
        "promoted from a layout alias",
        "through the src/lib layout alias",
        "took their layout alias's id",
        "imported under their layout alias",
    ),
    "registry-malformed": (
        "malformed entry: ",
        "duplicate key ",
        "missing a valid 'namespace'",
        "is not a relative POSIX path",
        "cannot be encoded as UTF-8",
        "id left to mint",
    ),
    "registry-path-key-unusable": (
        "keyed by its name",
        "imported under its name",
        "not recorded: no unique file",
        "stored by name",
        "keyed by their path as read",
        "is outside the project root",
    ),
    "registry-unknown-key": ("unknown top-level key", "has unknown key"),
    "registry-unusable": ("has no path relative to", "cannot be stored as"),
    "registry-wrong-format": (", expected 4",),
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
    "release-unusable": ("the file is yanked",),
    "requirement-invalid": ("optional and in no extra",),
    "requirement-unusable": ("not portable; skipped",),
    "sbom-invalid": (
        "SBOM is not valid",
        "@graph is not a list",
        "SBOM @graph",
        "SBOM cannot be read as SPDX 3",
        "the ID registry keeps its own",
    ),
    "sbom-wrong-format": ("named .spdx3.json but not SPDX 3",),
    "source-date-epoch-invalid": (
        "of seconds since the Unix epoch",
        "out of range for a date",
    ),
    "target-ambiguous": (
        "not an AI model file; reading its folder",
        "no Python project; reading this AI model file",
        "the one AI model file; reading it",
        "read as repository ",
        "not a repository; read as",
        ", not a folder; read as the file",
        ", not a file; reading it",
        "read as Hugging Face model ",
    ),
    "target-wrong-format": (
        "a Hugging Face model, not a project",
        "not a .whl file",
    ),
    "temp-dir-unusable": ("could not be saved in the temporary directory",),
    "temp-dir-unwritable": ("could not be fully removed",),
    "text-malformed": (
        "lone surrogates written",
        "cannot be encoded as UTF-8",
        "lone surrogates replaced with U+FFFD",
    ),
    "url-moved": ("; followed",),
    "url-unsafe": ("redirects to ", "; not fetched", " redirects; "),
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


@pytest.mark.parametrize(
    ("quote", "expected"),
    [
        ("INFO: ID registry: '<type>' <key> not imported: its id is held under", True),
        ("INFO: ID registry: <type> <key> not imported: its id is held under", True),
        # the held key prints unquoted: a free value is never one
        # placeholder in quotes (a quoted field is matched by its shape)
        ("ID registry: '<type>' <key> not imported: its id is held under '<k>'", False),
        ("ID registry: 'a_Type' 'k' not imported: its id is held under x", True),
    ],
    ids=["shown", "bare", "old-quotes", "value-quoted"],
)
def test_a_placeholder_in_quotes_is_a_quoted_field(quote: str, expected: bool) -> None:
    marker = "its id is held under"
    assert quote_matches(quote, "registry-conflict", marker) is expected
