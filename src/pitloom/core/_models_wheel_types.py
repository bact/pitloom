# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Shared types for per-backend wheel file discovery.

See also: :mod:`pitloom.core._models_wheel_dispatch` (dispatch facade),
:mod:`pitloom.core._models_wheel_hatchling`,
:mod:`pitloom.core._models_wheel_setuptools`.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple, Protocol, TypedDict

from pitloom.core.content_type_config import ContentTypeOverride

if TYPE_CHECKING:
    from pitloom.extract._file_headers import FileHeaderMetadata

BUILD_LOG_PREFIX = "Build: "
"""Shared ``WARNING:`` sub-prefix for every ``--allow-build``/build-and-
read-related log message (CLAUDE.md's "CLI output" convention: a shared,
literal sub-prefix so a subsystem's own messages are easy to grep/compare
as a group, matching the existing ``"Registry: "`` precedent). One
constant instead of a hand-copied literal at each call site -- see
CLAUDE.md's "a pattern hand-copied across 3+ call sites drifts" rule."""


class IncludedFile(NamedTuple):
    """One file that belongs in the wheel, as resolved by a backend.

    Mirrors the two attributes every backend-specific discoverer and
    Hatchling's own ``hatchling.builders.plugin.interface.IncludedFile``
    both expose, so the shared per-file processing loop in
    :mod:`pitloom.core._models_wheel` can consume either uniformly.
    """

    path: str
    distribution_path: str


# pylint: disable-next=too-few-public-methods
class BackendDiscoverer(Protocol):
    """Call signature every backend discovery module's ``discover()`` must
    share, so the dispatch registry in
    :mod:`pitloom.core._models_wheel_dispatch` can call any of them
    uniformly -- adding a new backend is then one
    module implementing this signature plus one registry entry, never a
    special case at the call site. *pyproject_data*, when given, is the
    already-parsed ``pyproject.toml`` (see
    :func:`pitloom.extract.project.setuptools.read_pyproject_toml`); a backend
    that doesn't need it (e.g. Hatchling, which re-reads config itself via
    ``WheelBuilder``) still accepts and ignores the keyword."""

    def __call__(
        self, project_dir: Path, *, pyproject_data: dict[str, object] | None = None
    ) -> list[IncludedFile] | None: ...


def has_resolvable_pyproject_config(
    pyproject_data: dict[str, object], backend: str
) -> bool:
    """Whether the parsed ``pyproject.toml`` declares enough for *backend*
    to resolve packages from: a PEP 621 ``[project]`` table (every
    registered backend's own zero-config auto-discovery applies here,
    even without an explicit ``[tool.<backend>]`` table) or an explicit
    ``[tool.<backend>]`` table. A ``pyproject.toml`` with only
    ``[build-system]`` (e.g. packages declared imperatively in
    ``setup.py`` instead) declares neither.

    Shared by :mod:`pitloom.core._models_wheel_setuptools` (deciding
    whether to attempt static discovery at all) and
    :mod:`pitloom.core._models_wheel_dispatch` (deciding what a failed
    discoverer's fallback ``WARNING:`` should say), so the two stay in
    sync rather than re-deriving the same check independently."""
    tool = pyproject_data.get("tool", {})
    return "project" in pyproject_data or (
        backend in tool if isinstance(tool, dict) else False
    )


_UV_BUILD_FILE_FILTER_KEYS = ("wheel-exclude", "wheel-include")
"""``[tool.uv.build-backend]`` keys that actually filter which files
reach the wheel -- deliberately narrower than every key that table can
hold. ``module-name``/``module-root``/``namespace`` change *where*
uv_build looks for the package, not which of its files it keeps, and
empirically make no difference to the resolved file set (the langfuse
fixture declares ``module-root`` and still matches the Hatchling
heuristic exactly -- see the validation round cited below); including
them here would warn on projects where the heuristic is already
correct, same false-positive-warning failure mode this check exists to
avoid on the *file list* itself."""


def has_uv_build_backend_overrides(pyproject_data: dict[str, object]) -> bool:
    """Whether the parsed ``pyproject.toml`` declares one of
    ``[tool.uv.build-backend]``'s file-filtering keys
    (:data:`_UV_BUILD_FILE_FILTER_KEYS`) with a non-empty value --
    uv_build-specific include/exclude directives that only uv_build
    itself understands.

    uv_build has no static discovery module of its own (see
    :mod:`pitloom.core._models_wheel_dispatch`), so the Hatchling-based
    heuristic fallback used in its place has no way to honor these --
    it can only see files that physically exist on disk, not a
    directive telling it to exclude some of them. Confirmed empirically
    (``working-docs/implementation/backend-file-discovery-validation.md``'s
    "``--allow-build`` build-and-read" round, 2026-09-15): a project
    with ``wheel-exclude`` populated is exactly the case where the
    fallback's file list diverges from the real wheel's (over-inclusion
    only, in the one case tested -- see that round's findings).

    Used only to sharpen the fallback's own ``WARNING:`` wording with a
    concrete pointer to ``--allow-build`` when this specific, known
    divergence risk is present -- never to change dispatch behavior
    itself, and never consulted for any backend other than uv_build."""
    tool = pyproject_data.get("tool")
    if not isinstance(tool, dict):
        return False
    uv = tool.get("uv")
    if not isinstance(uv, dict):
        return False
    build_backend = uv.get("build-backend")
    if not isinstance(build_backend, dict):
        return False
    return any(build_backend.get(key) for key in _UV_BUILD_FILE_FILTER_KEYS)


def is_dist_info_path(distribution_path: str) -> bool:
    """Whether *distribution_path* falls under a wheel's own
    ``<name>-<version>.dist-info/`` directory -- build-generated,
    never a project source file.

    No existing static backend module needs this: each one's underlying
    library (``recurse_included_files()``, ``find_files_to_add()``,
    ``WheelBuilder.get_files()``, ``Module.iter_files()``, setuptools'
    ``build_py``) never surfaces ``.dist-info`` paths from its own
    file-discovery entry point in the first place. This is the first
    consumer -- :mod:`pitloom.core._models_wheel_build_and_read`, which
    reads an already-built wheel's real zip contents (which genuinely
    does contain ``.dist-info``) and must filter it back out to match
    every other backend's ``IncludedFile`` contract of pre-build source
    files only.

    *distribution_path* MUST already be POSIX-normalized (see
    :func:`to_posix_distribution_path`) -- this function does no
    normalization of its own and will not recognize a
    backslash-separated path as a ``.dist-info`` path.
    """
    return "/" in distribution_path and distribution_path.split("/", 1)[0].endswith(
        ".dist-info"
    )


def to_posix_distribution_path(path: str) -> str:
    """Normalize *path* to forward-slash separators for use as an
    ``IncludedFile.distribution_path`` -- a wheel's internal paths are
    always ``/``-separated regardless of the platform Pitloom runs on.

    Shared so this one-line normalization doesn't keep getting
    hand-copied per backend discovery module (setuptools, Hatchling,
    Poetry, Flit each needed it independently) -- see CLAUDE.md's note
    that a pattern repeated across 3+ call sites drifts."""
    return path.replace("\\", "/")


class FileScanConfig(NamedTuple):
    """Optional per-file header/content-type scanner config, bundled so
    it threads through :mod:`pitloom.core._models_wheel`'s per-file
    helpers as one object instead of four separate parameters each.

    ``parse_header``/``detect_content`` are ``None`` when their
    respective scan (``scan_file_headers``/``detect_content_type``) is
    off -- see :func:`~pitloom.core._models_wheel._resolve_file_header_extras`,
    the sole consumer.
    """

    parse_header: Callable[[bytes], FileHeaderMetadata | None] | None
    detect_content: Callable[[bytes, str, str], tuple[str | None, str | None]] | None
    content_type_overrides: tuple[ContentTypeOverride, ...]
    content_type_method: str


class FileHeaderExtras(TypedDict):
    """Keyword arguments for :class:`~pitloom.core.project.ProjectFile`'s
    header/content-type fields."""

    copyright_text: str | None
    copyright_source: str | None
    file_contributors: list[str]
    file_type: str | None
    spdx_license_identifier: str | None
    content_type: str | None
    content_type_method: str | None


DEFAULT_BUILD_TIMEOUT_SECONDS = 1200
"""``--build-timeout`` default (20 minutes) when the caller gives none."""

MAX_BUILD_TIMEOUT_SECONDS = 604_800
"""``--build-timeout`` upper bound (7 days). There is no "0 = unlimited":
an unbounded build is exactly the hang the timeout exists to prevent."""


class BuildSettings(NamedTuple):
    """``--allow-build`` options, bundled so they thread through
    :mod:`pitloom.core._models_wheel_dispatch` as one value (``None`` there
    means ``--allow-build`` is off)."""

    isolated: bool
    timeout: int


# Out-of-range values of this magnitude are described, never formatted:
# str() of an int beyond sys.get_int_max_str_digits() raises ValueError.
_ECHO_LIMIT = 10**12


def _out_of_range(shown: str) -> ValueError:
    return ValueError(
        f"build timeout must be 1-{MAX_BUILD_TIMEOUT_SECONDS} seconds, got {shown}"
    )


def validate_build_timeout(value: object) -> int:
    """Return *value* if it is a valid build timeout in whole seconds.

    Raises :class:`TypeError` for a non-``int`` (``bool`` included, even
    though it subclasses ``int``) and :class:`ValueError` outside
    ``1..MAX_BUILD_TIMEOUT_SECONDS``. Messages carry no ``Build:`` prefix:
    argparse prefixes its own ``argument --build-timeout:``.
    """
    # bool subclasses int; True must not pass as a one-second timeout.
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(
            f"build timeout must be an int number of seconds, "
            f"got {type(value).__name__}"
        )
    if value > MAX_BUILD_TIMEOUT_SECONDS:
        shown = (
            str(value)
            if value < _ECHO_LIMIT
            else f"more than {MAX_BUILD_TIMEOUT_SECONDS}"
        )
        raise _out_of_range(shown)
    if value < 1:
        raise _out_of_range(str(value) if value > -_ECHO_LIMIT else "less than 1")
    return value


def resolve_build_timeout(value: int | None) -> int:
    """Return :data:`DEFAULT_BUILD_TIMEOUT_SECONDS` for ``None``, else the
    validated *value* (see :func:`validate_build_timeout`)."""
    if value is None:
        return DEFAULT_BUILD_TIMEOUT_SECONDS
    return validate_build_timeout(value)


# [0-9], not \d: \d also matches non-ASCII digits such as Arabic-Indic ones.
_BARE_SECONDS_RE = re.compile(r"[0-9]+")
_DURATION_RE = re.compile(r"(?:([0-9]+)h)?(?:([0-9]+)m)?(?:([0-9]+)s)?")
_UNIT_SECONDS = (3600, 60, 1)
_MAX_SIGNIFICANT_DIGITS = len(str(MAX_BUILD_TIMEOUT_SECONDS))


def parse_build_timeout(text: str) -> int:
    """Parse a CLI/GitHub Action duration string into validated seconds.

    Accepted: bare ASCII digits (seconds, e.g. ``900``), or ``h``/``m``/``s``
    units in that order, each at most once (``90m``, ``1h30m``,
    ``1h30m45s``). Every unit-bearing value accepted here means the same
    in Go's ``time.ParseDuration``. Components are not capped individually
    (``1h90m`` is fine); only the total is range-checked
    (see :func:`validate_build_timeout`).

    Rejected with :class:`ValueError`: decimals, ``ms``/``d`` units,
    upper-case units, signs, whitespace (never stripped), repeated or
    out-of-order units, and non-ASCII digits.
    """
    shown = text if len(text) <= 40 else f"{text[:40]}..."
    invalid = ValueError(
        f"invalid duration {shown!r} (use seconds, or h/m/s units like 1h30m)"
    )
    # No strip(): surrounding whitespace is an error, not trimmed.
    if _BARE_SECONDS_RE.fullmatch(text):
        parts: tuple[str | None, ...] = (None, None, text)
    else:
        match = _DURATION_RE.fullmatch(text)
        # The all-optional pattern also matches "", which is not a duration.
        if match is None or not any(match.groups()):
            raise invalid
        parts = match.groups()
    # int() refuses digit strings beyond sys.get_int_max_str_digits(), so
    # drop leading zeros first; a component with more significant digits
    # than the maximum is out of range whatever its unit.
    digits = [None if part is None else part.lstrip("0") or "0" for part in parts]
    if any(part and len(part) > _MAX_SIGNIFICANT_DIGITS for part in digits):
        raise _out_of_range(f"more than {MAX_BUILD_TIMEOUT_SECONDS}")
    seconds = sum(
        int(part) * unit
        for part, unit in zip(digits, _UNIT_SECONDS, strict=True)
        if part is not None
    )
    return validate_build_timeout(seconds)
