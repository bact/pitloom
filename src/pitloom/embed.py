# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Embed SPDX 3 SBOMs into built Python wheels (PEP 770)."""

from __future__ import annotations

import base64
import csv
import dataclasses
import email
import hashlib
import io
import json
import os
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3.document import build as assemble_spdx3
from pitloom.assemble.spdx3.fragments import merge_fragments
from pitloom.core.config import VALID_CONTENT_TYPE_METHODS, PitloomConfig
from pitloom.core.creation import CreationMetadata, resolve_source_date_epoch
from pitloom.core.document import DocumentModel
from pitloom.core.models import get_wheel_files
from pitloom.core.project import ProjectMetadata
from pitloom.core.provenance import ProvenanceConfig
from pitloom.enrich import run_enrichers_for_models
from pitloom.extract.binary import find_phantom_dependencies
from pitloom.extract.project import read_project
from pitloom.extract.scanner import scan_project_for_ai_models
from pitloom.extract.wheel import read_wheel
from pitloom.ids import IdRegistry, resolve_registry

__all__ = [
    "ConfigOverrides",
    "embed_sbom_in_wheel",
    "embed_wheel_sbom",
]

_SPDX3_JSON_EXT = ".spdx3.json"
_DEFAULT_FILE_ATTR = 0o644 << 16

#: Two different epoch floors are in play here, from unrelated conventions:
#: - Unix time (what ``SOURCE_DATE_EPOCH`` counts from) starts 1970-01-01 --
#:   ``SOURCE_DATE_EPOCH=0`` is a legitimate, deliberately-chosen value (some
#:   build systems use it as a fixed "don't care, just be deterministic"
#:   placeholder), not an error.
#: - The ZIP format's per-entry timestamp field (DOS date/time, inherited
#:   from MS-DOS's own timestamp format) can only represent 1980-01-01
#:   onward -- a binary format limitation, unrelated to Unix time or to
#:   what date is semantically correct.
#: A `SOURCE_DATE_EPOCH` between these two floors (or an unset entry with
#: no fallback, defaulting to the Unix epoch) is valid Unix time but not
#: representable in a ZIP entry, so it must be floored to 1980-01-01 for
#: the archive entry specifically -- see :func:`_resolve_zip_timestamp`.
#: The embedded SBOM's own ``created`` field has no such constraint (plain
#: JSON/ISO 8601) and is never floored, so the two can legitimately diverge;
#: callers surface this via the ``floored`` return value rather than
#: silently rewriting the SBOM's stated creation date to match the ZIP
#: format's limitation -- see :func:`~pitloom.core.creation.CreationMetadata`.
_ZIP_EPOCH_FLOOR = datetime(1980, 1, 1, tzinfo=timezone.utc)


def _find_dist_info_prefix(zf: zipfile.ZipFile, wheel_path: Path) -> str:
    """Find the single .dist-info directory prefix in the wheel ZIP archive."""
    dist_infos: set[str] = set()
    for name in zf.namelist():
        parts = name.split("/")
        if len(parts) >= 2 and parts[0].endswith(".dist-info"):
            dist_infos.add(f"{parts[0]}/")

    if not dist_infos:
        raise ValueError(
            f"Invalid wheel archive {wheel_path.name}: no .dist-info directory found"
        )
    if len(dist_infos) > 1:
        # Prefer dist-info matching the wheel file name prefix if ambiguous
        stem_prefix = wheel_path.stem.split("-")[0]
        matching = [
            d
            for d in dist_infos
            if d.startswith(f"{stem_prefix}-") or d == f"{stem_prefix}.dist-info/"
        ]
        if len(matching) == 1:
            return matching[0]
        raise ValueError(
            f"Invalid wheel archive {wheel_path.name}: multiple .dist-info "
            f"directories found ({sorted(dist_infos)})"
        )
    return next(iter(dist_infos))


def _resolve_zip_timestamp(
    fallback: tuple[int, int, int, int, int, int] | None = None,
) -> tuple[tuple[int, int, int, int, int, int], bool]:
    """Resolve entry timestamp respecting SOURCE_DATE_EPOCH if set.

    Returns ``(timestamp, floored)`` -- ``floored`` is ``True`` when the
    resolved value was below ``_ZIP_EPOCH_FLOOR`` and had to be bumped up
    to it, since the ZIP format (unlike the SBOM's own JSON ``created``
    field) cannot represent a pre-1980 date. Most commonly triggered by
    ``SOURCE_DATE_EPOCH=0``, a common reproducible-builds convention for
    "pin to a fixed placeholder" -- callers should surface ``floored`` to
    the user, since it means the embedded SBOM's stated ``created`` and
    the wheel archive's own entry timestamp now silently diverge.
    """
    epoch_dt = resolve_source_date_epoch()
    if epoch_dt is not None:
        clamped = max(epoch_dt, _ZIP_EPOCH_FLOOR)
        return (
            (
                clamped.year,
                clamped.month,
                clamped.day,
                clamped.hour,
                clamped.minute,
                clamped.second,
            ),
            clamped != epoch_dt,
        )
    if fallback is not None:
        if fallback[0] >= 1980:
            return fallback, False
        return (1980, 1, 1, 0, 0, 0), True
    now = datetime.now(timezone.utc)
    return (now.year, now.month, now.day, now.hour, now.minute, now.second), False


def _calculate_record_hash(content: bytes) -> str:
    """Compute base64url SHA-256 digest without trailing padding (PEP 376)."""
    digest = hashlib.sha256(content).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _looks_like_pitloom_sbom(content: bytes) -> bool:
    """Check whether an SPDX 3 JSON-LD payload was created by Pitloom.

    Used to decide whether a pre-existing ``sboms/`` entry left by an
    earlier run under a different filename is safe to clean up on
    re-embed. PEP 770 allows multiple SBOMs from different tools to
    coexist under ``sboms/``, so cleanup must not touch anything that
    doesn't look like Pitloom's own prior output -- malformed/unparseable
    content or the absence of a ``Tool``/``SoftwareAgent`` named
    ``"Pitloom"`` in ``@graph`` means "leave it alone".
    """
    try:
        doc = json.loads(content)
    except (ValueError, UnicodeDecodeError):
        return False
    graph = doc.get("@graph") if isinstance(doc, dict) else None
    if not isinstance(graph, list):
        return False
    return any(
        isinstance(node, dict)
        and node.get("type") in ("Tool", "SoftwareAgent")
        and node.get("name") == "Pitloom"
        for node in graph
    )


def _update_record_lines(
    record_text: str,
    sbom_arcname: str,
    sbom_hash: str,
    sbom_size: int,
    dist_info_prefix: str,
    stale_arcnames: frozenset[str] = frozenset(),
) -> str:
    """Update or insert the SBOM entry in RECORD and ensure RECORD,, is intact.

    ``stale_arcnames`` are prior Pitloom-embedded SBOM entries (e.g. left
    behind by an earlier run under a different basename) whose rows are
    dropped so RECORD does not go stale relative to the rewritten archive.
    """
    rows: list[list[str]] = []
    reader = csv.reader(io.StringIO(record_text))
    found_sbom = False
    record_arcname = f"{dist_info_prefix}RECORD"

    for row in reader:
        if not row:
            continue
        if row[0] == sbom_arcname:
            rows.append([sbom_arcname, f"sha256={sbom_hash}", str(sbom_size)])
            found_sbom = True
        elif row[0] == record_arcname or row[0] in stale_arcnames:
            continue
        else:
            rows.append(row)

    if not found_sbom:
        rows.append([sbom_arcname, f"sha256={sbom_hash}", str(sbom_size)])

    rows.append([record_arcname, "", ""])

    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerows(rows)
    return out.getvalue()


def embed_sbom_in_wheel(
    wheel_path: Path | str,
    sbom_content: str | bytes,
    *,
    sbom_filename: str | None = None,
) -> tuple[Path, str, tuple[str, ...], bool]:
    """Embed an SPDX 3 SBOM into a built wheel archive (PEP 770).

    Args:
        wheel_path: Path to the target .whl file to modify in place.
        sbom_content: Raw SBOM JSON-LD content (string or bytes).
        sbom_filename: Custom filename inside .dist-info/sboms/.
            Defaults to '<name>-<version>.spdx3.json' read from wheel metadata.

    Returns:
        A tuple of (wheel_path, embedded_arcname, removed_arcnames,
        zip_timestamp_floored). ``embedded_arcname`` is the relative path
        inside the wheel (e.g. 'pkg-1.0.dist-info/sboms/pkg-1.0.spdx3.json').
        ``removed_arcnames`` lists any prior Pitloom-embedded SBOM entries
        (under a different filename) that were cleaned up as part of this
        embed -- see :func:`_looks_like_pitloom_sbom`. ``zip_timestamp_floored``
        is ``True`` when the resolved entry timestamp was before 1980 and
        had to be bumped up to the ZIP format's floor -- see
        :func:`_resolve_zip_timestamp`; the embedded SBOM's own ``created``
        is unaffected and keeps the true (possibly pre-1980) value.

    Raises:
        ValueError: If the wheel archive has no valid .dist-info directory.
        FileNotFoundError: If the wheel file does not exist.
    """
    wheel_obj = Path(wheel_path).resolve()
    if not wheel_obj.exists():
        raise FileNotFoundError(f"Wheel file not found: {wheel_obj}")

    sbom_bytes = (
        sbom_content.encode("utf-8") if isinstance(sbom_content, str) else sbom_content
    )
    if not sbom_bytes.strip():
        raise ValueError("SBOM content cannot be empty")

    orig_mode = wheel_obj.stat().st_mode if wheel_obj.exists() else None

    with zipfile.ZipFile(wheel_obj, "r") as original_zf:
        dist_info = _find_dist_info_prefix(original_zf, wheel_obj)
        plan = _plan_embed(original_zf, dist_info, sbom_filename, sbom_bytes)
        temp_path = _rewrite_wheel_archive(
            wheel_obj,
            original_zf,
            plan.sbom_arcname,
            sbom_bytes,
            plan.record_arcname,
            plan.new_record_bytes,
            plan.timestamp,
            plan.stale_arcnames,
        )

    try:
        os.replace(temp_path, wheel_obj)
        if orig_mode is not None:
            try:
                os.chmod(wheel_obj, orig_mode)
            except OSError:
                pass
    finally:
        if temp_path.exists():
            temp_path.unlink()

    return (
        wheel_obj,
        plan.sbom_arcname,
        tuple(sorted(plan.stale_arcnames)),
        plan.timestamp_floored,
    )


@dataclasses.dataclass(frozen=True)
class _EmbedPlan:
    """Everything :func:`embed_sbom_in_wheel` needs to rewrite the archive."""

    sbom_arcname: str
    record_arcname: str
    new_record_bytes: bytes
    stale_arcnames: frozenset[str]
    timestamp: tuple[int, int, int, int, int, int]
    timestamp_floored: bool


def _plan_embed(
    original_zf: zipfile.ZipFile,
    dist_info: str,
    sbom_filename: str | None,
    sbom_bytes: bytes,
) -> _EmbedPlan:
    """Resolve the target arcname, updated RECORD, and ZIP timestamp for an embed."""
    target_name = (
        sbom_filename
        if sbom_filename is not None
        else _derive_wheel_sbom_filename(original_zf, dist_info)
    )
    _validate_sbom_filename(target_name)
    sbom_arcname = f"{dist_info}sboms/{target_name}"
    record_arcname = f"{dist_info}RECORD"
    sboms_prefix = f"{dist_info}sboms/"
    stale_arcnames = frozenset(
        name
        for name in original_zf.namelist()
        if name.startswith(sboms_prefix)
        and name.endswith(_SPDX3_JSON_EXT)
        and name != sbom_arcname
        and _looks_like_pitloom_sbom(original_zf.read(name))
    )

    record_info = None
    for info in original_zf.infolist():
        if info.filename == record_arcname:
            record_info = info
            break

    old_record_text = (
        original_zf.read(record_arcname).decode("utf-8") if record_info else ""
    )
    new_record_text = _update_record_lines(
        old_record_text,
        sbom_arcname,
        _calculate_record_hash(sbom_bytes),
        len(sbom_bytes),
        dist_info,
        stale_arcnames,
    )

    timestamp, timestamp_floored = _resolve_zip_timestamp(
        record_info.date_time if record_info else None
    )
    return _EmbedPlan(
        sbom_arcname=sbom_arcname,
        record_arcname=record_arcname,
        new_record_bytes=new_record_text.encode("utf-8"),
        stale_arcnames=stale_arcnames,
        timestamp=timestamp,
        timestamp_floored=timestamp_floored,
    )


_INVALID_FILENAME_CHARS = frozenset({"/", "\\", "\x00"})


def _validate_sbom_filename(filename: str) -> None:
    """Guard against path traversal in an embedded SBOM filename (CWE-22).

    ``filename`` may come from wheel METADATA (untrusted archive content)
    or a user-supplied ``--sbom-basename``, so it must resolve to a plain
    filename with no path separators or traversal segments.
    """
    clean = filename.strip()
    if (
        not clean
        or clean in (".", "..")
        or any(c in clean for c in _INVALID_FILENAME_CHARS)
    ):
        raise ValueError(f"Invalid SBOM filename: {filename!r}")


def _derive_wheel_sbom_filename(zf: zipfile.ZipFile, dist_info: str) -> str:
    """Derive default SBOM filename from wheel METADATA."""
    meta_name: str | None = None
    meta_version: str | None = None
    metadata_path = f"{dist_info}METADATA"
    if metadata_path in zf.namelist():
        content = zf.read(metadata_path).decode("utf-8", errors="replace")
        msg = email.message_from_string(content)
        meta_name = msg.get("Name")
        meta_version = msg.get("Version")
    if meta_name and meta_version:
        return f"{meta_name}-{meta_version}{_SPDX3_JSON_EXT}"
    prefix = dist_info.rstrip("/").removesuffix(".dist-info")
    return f"{prefix}{_SPDX3_JSON_EXT}" if prefix else f"sbom{_SPDX3_JSON_EXT}"


def _rewrite_wheel_archive(
    wheel_path: Path,
    original_zf: zipfile.ZipFile,
    sbom_arcname: str,
    sbom_bytes: bytes,
    record_arcname: str,
    record_bytes: bytes,
    timestamp: tuple[int, int, int, int, int, int],
    stale_arcnames: frozenset[str] = frozenset(),
) -> Path:
    """Write updated entries to a temporary file.

    ``stale_arcnames`` are dropped from the rewritten archive rather than
    copied through -- see :func:`_looks_like_pitloom_sbom`.
    """
    temp_dir = wheel_path.parent
    with tempfile.NamedTemporaryFile(
        dir=temp_dir,
        delete=False,
        prefix=f"{wheel_path.stem}.",
        suffix=".tmp",
    ) as temp_file:
        temp_path = Path(temp_file.name)

    try:
        with zipfile.ZipFile(
            temp_path, "w", compression=zipfile.ZIP_DEFLATED
        ) as new_zf:
            for info in original_zf.infolist():
                if info.filename in (record_arcname, sbom_arcname):
                    continue
                if info.filename in stale_arcnames:
                    continue
                with original_zf.open(info, "r") as src, new_zf.open(info, "w") as dst:
                    shutil.copyfileobj(src, dst)

            sbom_info = zipfile.ZipInfo(sbom_arcname, date_time=timestamp)
            sbom_info.compress_type = zipfile.ZIP_DEFLATED
            sbom_info.external_attr = _DEFAULT_FILE_ATTR
            new_zf.writestr(sbom_info, sbom_bytes)

            rec_info = zipfile.ZipInfo(record_arcname, date_time=timestamp)
            rec_info.compress_type = zipfile.ZIP_DEFLATED
            rec_info.external_attr = _DEFAULT_FILE_ATTR
            new_zf.writestr(rec_info, record_bytes)

        return temp_path
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise


def _build_sbom_from_project_and_wheel(
    project_dir: Path,
    wheel_metadata: ProjectMetadata,
    pitloom_config: PitloomConfig,
    registry: IdRegistry | None,
    creation_metadata: CreationMetadata | None,
) -> str:
    """Generate a canonical Build SBOM from project sources and wheel files."""
    merkle_root, project_files = get_wheel_files(
        project_dir,
        scan_file_headers=pitloom_config.extract_file_header,
        detect_content_type=pitloom_config.content_type.enabled,
        content_type_method=pitloom_config.content_type.method,
        content_type_overrides=pitloom_config.content_type.overrides,
    )
    ai_models = scan_project_for_ai_models(project_dir, project_files)
    phantom_deps = find_phantom_dependencies(wheel_metadata.files)
    enrichment_results = run_enrichers_for_models(
        ai_models, pitloom_config.enrich, project_dir
    )

    doc = DocumentModel(
        project=wheel_metadata,
        creation_metadata=creation_metadata or CreationMetadata(),
        ai_models=ai_models,
        phantom_dependencies=phantom_deps,
    )
    exporter = assemble_spdx3(
        doc,
        merkle_root=merkle_root,
        sbom_type=spdx3.software_SbomType.build,
        registry=registry,
        provenance=pitloom_config.provenance,
        enrichment_results_by_model=enrichment_results,
        offline=pitloom_config.offline,
    )
    merge_fragments(project_dir, pitloom_config.fragments, exporter)
    return exporter.to_json(pretty=False)


@dataclasses.dataclass(frozen=True)
class ConfigOverrides:
    """Per-run overrides layered onto a project's ``[tool.pitloom]`` config.

    Each field defaults to ``None`` (defer to the project's own config, or
    its own built-in default when there is no project) -- see
    :func:`_apply_config_overrides`.
    """

    provenance: ProvenanceConfig | None = None
    enrich: bool | None = None
    extract_file_header: bool | None = None
    content_type: bool | None = None
    content_type_method: str | None = None
    offline: bool | None = None


# pylint: disable=too-many-arguments
def embed_wheel_sbom(
    wheel_path: Path | str,
    *,
    project_dir: Path | str | None = None,
    pitloom_config: PitloomConfig | None = None,
    sbom_path: Path | str | None = None,
    output_path: Path | str | None = None,
    sbom_basename: str | None = None,
    creation_metadata: CreationMetadata | None = None,
    registry: str | Path | IdRegistry | None = None,
    overrides: ConfigOverrides | None = None,
) -> tuple[Path, str, str, tuple[str, ...], bool]:
    """Generate and embed a PEP 770 SBOM into a built Python wheel.

    Args:
        wheel_path: Path to the target .whl file.
        project_dir: Optional source project root containing pyproject.toml.
        project_metadata: Optional pre-parsed project metadata.
        pitloom_config: Optional pre-parsed pitloom config.
        sbom_path: Optional path to a pre-generated SBOM to embed directly.
        output_path: Optional path to write a standalone copy of the SBOM.
        sbom_basename: Custom basename for the embedded SBOM file.
        creation_metadata: Optional creation metadata overrides.
        registry: ID registry or path.
        overrides: Per-run overrides for provenance/enrich/content-type/offline
            settings, layered onto the project's ``[tool.pitloom]`` config.
            Defaults to no overrides.

    Returns:
        Tuple of (modified_wheel_path, embedded_arcname, sbom_json_string,
        removed_arcnames, zip_timestamp_floored) -- see
        :func:`embed_sbom_in_wheel`.
    """
    wheel_obj = Path(wheel_path).resolve()
    wheel_metadata, _ = read_wheel(wheel_obj)
    eff_overrides = overrides if overrides is not None else ConfigOverrides()

    sbom_json, eff_basename = _generate_embed_sbom_json(
        wheel_metadata,
        project_dir=project_dir,
        pitloom_config=pitloom_config,
        sbom_path=sbom_path,
        sbom_basename=sbom_basename,
        creation_metadata=creation_metadata,
        registry=registry,
        overrides=eff_overrides,
    )
    target_filename = (
        f"{eff_basename.removesuffix(_SPDX3_JSON_EXT)}{_SPDX3_JSON_EXT}"
        if eff_basename
        else None
    )

    res_path, arcname, removed_arcnames, timestamp_floored = embed_sbom_in_wheel(
        wheel_obj, sbom_json, sbom_filename=target_filename
    )

    if output_path is not None:
        Path(output_path).write_text(sbom_json, encoding="utf-8")

    return res_path, arcname, sbom_json, removed_arcnames, timestamp_floored


# pylint: disable=too-many-arguments
def _generate_embed_sbom_json(
    wheel_metadata: ProjectMetadata,
    *,
    project_dir: Path | str | None,
    pitloom_config: PitloomConfig | None,
    sbom_path: Path | str | None,
    sbom_basename: str | None,
    creation_metadata: CreationMetadata | None,
    registry: str | Path | IdRegistry | None,
    overrides: ConfigOverrides,
) -> tuple[str, str | None]:
    """Resolve the SBOM JSON to embed and its effective basename.

    A pre-generated ``sbom_path`` wins outright; otherwise a source project
    (if found) drives a Build SBOM, falling back to a standalone Analyzed
    SBOM from wheel contents alone -- see :func:`embed_wheel_sbom`.
    """
    if sbom_path is not None:
        return Path(sbom_path).read_text(encoding="utf-8"), sbom_basename

    if project_dir is None:
        sbom_json = _build_sbom_standalone_wheel(
            wheel_metadata,
            creation_metadata,
            registry,
            overrides.provenance,
            overrides.offline,
        )
        return sbom_json, sbom_basename

    proj_root = Path(project_dir).resolve()
    if pitloom_config is None:
        _, cfg, _ = read_project(proj_root)
    else:
        cfg = pitloom_config

    cfg = _apply_config_overrides(cfg, overrides)
    eff_registry = registry if registry is not None else cfg.ids_file
    reg = resolve_registry(proj_root, eff_registry)
    sbom_json = _build_sbom_from_project_and_wheel(
        proj_root, wheel_metadata, cfg, reg, creation_metadata or cfg.creation_metadata
    )
    return sbom_json, sbom_basename or cfg.sbom_basename


def _apply_config_overrides(
    cfg: PitloomConfig, overrides: ConfigOverrides
) -> PitloomConfig:
    """Apply per-run overrides to a PitloomConfig."""
    changes: dict[str, Any] = {}
    if overrides.provenance is not None:
        changes["provenance_format"] = overrides.provenance.format
        changes["provenance_schema"] = overrides.provenance.schema
        changes["provenance_detail"] = overrides.provenance.detail
        changes["provenance_preserve_source_metadata"] = (
            overrides.provenance.preserve_source_metadata
        )
    if overrides.enrich is not None:
        changes["enrich_local"] = overrides.enrich
    if overrides.extract_file_header is not None:
        changes["extract_file_header"] = overrides.extract_file_header
    if overrides.content_type is not None:
        changes["content_type_enabled"] = overrides.content_type
    if overrides.content_type_method is not None:
        if overrides.content_type_method not in VALID_CONTENT_TYPE_METHODS:
            raise ValueError(
                "content_type_method must be one of "
                f"{sorted(VALID_CONTENT_TYPE_METHODS)}, got "
                f"{overrides.content_type_method!r}"
            )
        changes["content_type_method"] = overrides.content_type_method
    if overrides.offline is not None:
        changes["offline"] = overrides.offline
    return dataclasses.replace(cfg, **changes)


def _build_sbom_standalone_wheel(
    wheel_metadata: ProjectMetadata,
    creation_metadata: CreationMetadata | None,
    registry: str | Path | IdRegistry | None,
    provenance: ProvenanceConfig | None,
    offline: bool | None,
) -> str:
    """Build SBOM from standalone wheel when no source project dir is present."""
    reg = resolve_registry(Path.cwd(), registry)
    doc = DocumentModel(
        project=wheel_metadata,
        creation_metadata=creation_metadata or CreationMetadata(),
        ai_models=[],
        phantom_dependencies=find_phantom_dependencies(wheel_metadata.files),
    )
    exporter = assemble_spdx3(
        doc,
        merkle_root=None,
        sbom_type=spdx3.software_SbomType.analyzed,
        registry=reg,
        provenance=provenance,
        offline=offline or False,
    )
    return exporter.to_json(pretty=False)
