# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Built-wheel producer for the AI model scanner.

A model is copied out of the wheel one member at a time, into a file named
``{member index}{suffix}`` in a temporary directory: nothing else of the
archive name reaches the file system, and no temporary path reaches the SBOM
or a log line.
The copy is bounded per model by a ceiling, and per wheel by a budget of
several ceilings; neither trusts the archive's declared size.

See also: :mod:`pitloom.extract.scanner` (the shared policy),
:mod:`pitloom.extract.scanner_project` (the project producer) and
:mod:`pitloom.core.archive_member_names` (member names).
"""

from __future__ import annotations

import contextlib
import importlib
import logging
import lzma
import os
import zipfile
import zlib
from collections.abc import Callable, Iterable, Iterator
from contextlib import AbstractContextManager
from pathlib import Path, PurePosixPath
from typing import IO, NoReturn

from packaging.utils import (
    InvalidWheelFilename,
    canonicalize_name,
    parse_wheel_filename,
)
from packaging.version import InvalidVersion, Version

from pitloom.core.ai_metadata import AiModelFormat, AiModelMetadata
from pitloom.core.archive_member_names import zip_file_members
from pitloom.core.build_signals import MODEL_SCAN_ACTIVITY, TerminationGuard
from pitloom.core.model_extract_limit import require_max_model_extract_bytes
from pitloom.core.temp_dirs import registered_temp_dir
from pitloom.extract.ai_model import SNIFF_BYTES
from pitloom.extract.ai_model.limits import ScanBudgetExceeded, charging_reads
from pitloom.extract.scanner import (
    USAGE_SETTING_WHEEL,
    ModelCandidate,
    ModelTooLarge,
    ReaderGate,
    UsageSource,
    scan_ai_models,
)
from pitloom.logging_config import loggable

log = logging.getLogger(__name__)

_CHUNK_BYTES = 8192


def _zstd_errors() -> tuple[type[Exception], ...]:
    """``compression.zstd.ZstdError`` where zipfile can read Zstandard members
    (Python 3.14+); detected by importing, not by version."""
    try:
        module = importlib.import_module("compression.zstd")
    except ImportError:
        return ()
    error = getattr(module, "ZstdError", None)
    return (error,) if isinstance(error, type) else ()


# Everything a damaged, encrypted or unsupported member raises on reading.
_MEMBER_READ_ERRORS: tuple[type[Exception], ...] = (
    RuntimeError,
    NotImplementedError,
    zlib.error,
    lzma.LZMAError,
    EOFError,
    zipfile.BadZipFile,
    *_zstd_errors(),
)

_Member = tuple[str, zipfile.ZipInfo]


#: Formats whose reader is not run on a wheel's files unless the caller
#: trusts the wheel (``--trust-wheel-model``): a native parser (fastText,
#: HDF5, ONNX), a pickle parser (PyTorch ``.pt``/``.pth``, through
#: fickling) or a per-element Python loop (GGUF) that a hostile file can
#: crash, hang or exhaust memory in. Add a
#: format here to gate it; nothing else changes. Project scans are not gated.
WHEEL_GATED_FORMATS = frozenset(
    {
        AiModelFormat.FASTTEXT,
        AiModelFormat.GGUF,
        AiModelFormat.HDF5,
        AiModelFormat.ONNX,
        AiModelFormat.PYTORCH,
    }
)

#: The wheel's overall extraction budget, in multiples of the per-model ceiling.
BUDGET_FACTOR = 4


class _Scratch:
    """What one wheel scan copies into: a temporary directory made on first
    use (a wheel without models creates none and arms no signal handler),
    and the budget of bytes it may copy and read in all (the bounded reads
    of archive members inside a model count too)."""

    def __init__(self, guard: TerminationGuard, max_bytes: int, wheel: str) -> None:
        self.guard = guard
        self.wheel = wheel
        self.max_bytes = max_bytes
        self.budget = BUDGET_FACTOR * max_bytes
        self.spent = 0
        self.exhausted = False
        self._path: Path | None = None
        self._remove: Callable[[], None] | None = None

    def path(self) -> Path:
        """The directory, created (inside a hold) on the first call."""
        if self._path is None:
            with self.guard.hold(MODEL_SCAN_ACTIVITY):
                self._path, self._remove = registered_temp_dir(
                    self.guard,
                    "pitloom-model-scan-",
                    log_prefix=MODEL_SCAN_ACTIVITY.log_prefix,
                )
        return self._path

    def remove(self) -> None:
        """Remove the directory when it was made."""
        if self._remove is not None:
            self._remove()

    def spend(self, size: int) -> None:
        """Count *size* bytes copied or read.

        Raises:
            ScanBudgetExceeded: The budget is spent (logged once).
        """
        self.spent += size
        if self.spent > self.budget:
            self.exhaust()

    def exhaust(self) -> NoReturn:
        """Stop copying for the rest of the wheel, saying so once."""
        if not self.exhausted:
            self.exhausted = True
            log.warning(
                "%sthe per-wheel budget of %d bytes for copying and reading "
                "model files in %s is spent; the model that would pass it and "
                "the models not yet read are listed without metadata",
                MODEL_SCAN_ACTIVITY.log_prefix,
                self.budget,
                loggable(self.wheel),
            )
        raise ScanBudgetExceeded


def _sniffer(zf: zipfile.ZipFile, info: zipfile.ZipInfo) -> Callable[[], bytes]:
    def _sniff() -> bytes:
        try:
            with zf.open(info) as fh:
                return fh.read(SNIFF_BYTES)
        except _MEMBER_READ_ERRORS as exc:
            raise OSError(str(exc)) from exc

    return _sniff


def _opener(
    zf: zipfile.ZipFile, info: zipfile.ZipInfo
) -> Callable[[], AbstractContextManager[IO[bytes]]]:
    def _open() -> AbstractContextManager[IO[bytes]]:
        return zf.open(info)

    return _open


def _copy_out(
    zf: zipfile.ZipFile, info: zipfile.ZipInfo, target: Path, scratch: _Scratch
) -> None:
    """Copy the member to the new file *target*. The declared size is only a
    prefilter: the copy stops once it reads more than the per-model ceiling,
    or the wheel's budget is spent."""
    # The member first: one that cannot be read leaves no file behind.
    with zf.open(info) as src, open(target, "xb") as dst:
        copied = 0
        while chunk := src.read(_CHUNK_BYTES):
            scratch.guard.raise_if_pending()
            copied += len(chunk)
            if copied > scratch.max_bytes:
                raise ModelTooLarge(None, scratch.max_bytes)
            scratch.spend(len(chunk))
            dst.write(chunk)


def _unlink_quietly(target: Path | None) -> None:
    """Delete *target*; a failure is left to the directory's removal."""
    if target is None:
        return
    try:
        os.unlink(target)
    except FileNotFoundError:
        pass
    except OSError as exc:
        log.debug("could not remove a copied model: %s", exc.strerror)


def _materializer(
    zf: zipfile.ZipFile, member: _Member, index: int, scratch: _Scratch
) -> Callable[[], AbstractContextManager[Path]]:
    name, info = member
    suffix = PurePosixPath(name).suffix.lower()

    @contextlib.contextmanager
    def _materialize() -> Iterator[Path]:
        if info.file_size > scratch.max_bytes:
            raise ModelTooLarge(info.file_size, scratch.max_bytes)
        if scratch.exhausted or scratch.spent + info.file_size > scratch.budget:
            scratch.exhaust()
        target: Path | None = None
        try:
            # Held as a whole: a signal waits for the copy to end or stop.
            with scratch.guard.hold(MODEL_SCAN_ACTIVITY):
                try:
                    target = scratch.path() / f"{index}{suffix}"
                    _copy_out(zf, info, target, scratch)
                except OSError as exc:
                    # Its text would name the temporary path.
                    raise OSError(
                        exc.errno, exc.strerror or type(exc).__name__
                    ) from None
            with charging_reads(scratch.spend):
                yield target
        finally:
            _unlink_quietly(target)

    return _materialize


def _is_dist_info_of(directory: str, name: str, version: Version) -> bool:
    """Whether top-level *directory* is ``<name>-<version>.dist-info`` for the
    canonical *name* and *version*, compared as the ecosystem does (PEP 503
    names, PEP 440 versions): ``My.Pkg-1.0`` is ``my_pkg-1.0.0``."""
    suffix = ".dist-info"
    distribution, dash, release = directory[: -len(suffix)].partition("-")
    if not (directory.endswith(suffix) and dash):
        return False
    try:
        return canonicalize_name(distribution) == name and Version(release) == version
    except InvalidVersion:
        return False


def _own_dist_info_prefixes(
    wheel_name: str, members: Iterable[_Member]
) -> tuple[str, ...]:
    """``"<dir>/"`` for each top-level directory that is the ``.dist-info``
    of the wheel *wheel_name* names (PEP 427): its own, as opposed to any
    other ``*.dist-info`` directory a wheel ships as data, which a hostile
    wheel may add with a fake ``METADATA`` or ``WHEEL`` to hide a model.

    Nothing is the wheel's own where *wheel_name* is not a wheel file name
    (a library caller may pass any path): every member is then scanned.
    """
    try:
        name, version, _, _ = parse_wheel_filename(wheel_name)
    except InvalidWheelFilename:
        return ()
    return tuple(
        sorted(
            {
                f"{parts[0]}/"
                for member_name, _ in members
                if len(parts := member_name.split("/")) > 1
                and _is_dist_info_of(parts[0], name, version)
            }
        )
    )


def _wheel_candidates(
    zf: zipfile.ZipFile,
    members: list[_Member],
    scratch: _Scratch,
    gate: ReaderGate | None,
) -> Iterator[ModelCandidate]:
    """One :class:`ModelCandidate` per member; no member is read here."""
    for index, member in enumerate(members):
        name, info = member
        yield ModelCandidate(
            distribution_path=name,
            physical_path=info.orig_filename,
            sniff=_sniffer(zf, info),
            materialize=_materializer(zf, member, index, scratch),
            gate=gate,
        )


def _wheel_sources(
    zf: zipfile.ZipFile, members: Iterable[_Member]
) -> Iterator[UsageSource]:
    """One :class:`UsageSource` per member; no member is read here."""
    for name, info in members:
        yield UsageSource(
            distribution_path=name,
            physical_path=info.orig_filename,
            open=_opener(zf, info),
        )


def scan_wheel_for_ai_models(
    wheel_path: Path,
    *,
    scan_usage: bool,
    usage_hint: Callable[[], bool],
    max_bytes: int,
    trust: bool = False,
    gate_hint: Callable[[AiModelFormat], bool] = lambda _fmt: True,
) -> list[AiModelMetadata]:
    """Scan a built wheel's files for AI models; with *scan_usage*, their
    script usages.

    Members are the wheel's install-location names as
    :func:`pitloom.extract.wheel.read_wheel` records them, minus the
    wheel's own ``.dist-info`` directory (the one its file name names; every
    member where it is not a wheel file name). A
    model's ``distribution_path`` is that name and its ``physical_path`` the
    raw archive name.

    A model larger than *max_bytes*, declared or actually read, or met once
    the wheel's budget (:data:`BUDGET_FACTOR` times *max_bytes*) of bytes
    copied and read is spent, stays in the result without metadata, with one
    ``WARNING:`` (per model for the ceiling, one per wheel for the budget).

    A model in a :data:`WHEEL_GATED_FORMATS` format is not read unless
    *trust*: it stays in the result without metadata, and one ``INFO:``
    line per scan names the flag and lists the gated formats met that
    *gate_hint* accepts (called once per format; a batch makes it claim a
    once-per-run slot for that format, so each format is named once).

    *usage_hint*: see :func:`pitloom.extract.scanner.scan_ai_models`.

    Models come back sorted; see
    :func:`pitloom.extract.scanner.discover_ai_models`.
    """
    # Only a library PitloomConfig reaches here unvalidated.
    require_max_model_extract_bytes(max_bytes, "pitloom_config")
    with zipfile.ZipFile(wheel_path) as zf, TerminationGuard() as guard:
        # No logger: read_wheel() already reported every member name.
        all_members = zip_file_members(zf, wheel_path.name, None)
        own = _own_dist_info_prefixes(wheel_path.name, all_members)
        members = [m for m in all_members if not m[0].startswith(own)]
        scratch = _Scratch(guard, max_bytes, wheel_path.name)
        gate = None if trust else ReaderGate(WHEEL_GATED_FORMATS, gate_hint)
        try:
            models = scan_ai_models(
                _wheel_candidates(zf, members, scratch, gate),
                _wheel_sources(zf, members),
                scan_usage=scan_usage,
                usage_hint=usage_hint,
                usage_setting=USAGE_SETTING_WHEEL,
            )
        finally:
            scratch.remove()
        # Only a scan that succeeded lists its gated models: on failure no
        # SBOM is written, and the line would describe one that is not.
        if gate is not None:
            gate.report()
        return models
