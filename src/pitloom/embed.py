# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Embed SPDX 3 SBOMs into built Python wheels (PEP 770)."""

from __future__ import annotations

import base64
import csv
import dataclasses
import hashlib
import io
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
from pitloom.core.creation import CreationMetadata
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

_SPDX3_JSON_EXT = ".spdx3.json"
_DEFAULT_FILE_ATTR = 0o644 << 16
_ZIP_EPOCH_MIN = 315532800  # 1980-01-01T00:00:00Z, earliest zipfile supports


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
        matching = [d for d in dist_infos if d.startswith(stem_prefix)]
        if len(matching) == 1:
            return matching[0]
        raise ValueError(
            f"Invalid wheel archive {wheel_path.name}: multiple .dist-info "
            f"directories found ({sorted(dist_infos)})"
        )
    return next(iter(dist_infos))


def _resolve_zip_timestamp(
    fallback: tuple[int, int, int, int, int, int] | None = None,
) -> tuple[int, int, int, int, int, int]:
    """Resolve entry timestamp respecting SOURCE_DATE_EPOCH if set."""
    source_date_epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if source_date_epoch:
        try:
            epoch = max(int(source_date_epoch), _ZIP_EPOCH_MIN)
            dt = datetime.fromtimestamp(epoch, tz=timezone.utc)
            return (dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)
        except (ValueError, OverflowError, OSError):
            pass
    if fallback is not None:
        return fallback
    now = datetime.now(timezone.utc)
    return (now.year, now.month, now.day, now.hour, now.minute, now.second)


def _calculate_record_hash(content: bytes) -> str:
    """Compute base64url SHA-256 digest without trailing padding (PEP 376)."""
    digest = hashlib.sha256(content).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _update_record_lines(
    record_text: str,
    sbom_arcname: str,
    sbom_hash: str,
    sbom_size: int,
    dist_info_prefix: str,
    stale_arcnames: frozenset[str] = frozenset(),
) -> str:
    """Update or insert the SBOM entry in RECORD and ensure RECORD,, is intact.

    ``stale_arcnames`` are prior embedded-SBOM entries (e.g. left behind by
    an earlier run under a different basename) whose rows are dropped so
    RECORD does not go stale relative to the rewritten archive.
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
) -> tuple[Path, str]:
    """Embed an SPDX 3 SBOM into a built wheel archive (PEP 770).

    Args:
        wheel_path: Path to the target .whl file to modify in place.
        sbom_content: Raw SBOM JSON-LD content (string or bytes).
        sbom_filename: Custom filename inside .dist-info/sboms/.
            Defaults to '<name>-<version>.spdx3.json' read from wheel metadata.

    Returns:
        A tuple of (wheel_path, embedded_arcname), where embedded_arcname is
        the relative path inside the wheel (e.g.
        'pkg-1.0.dist-info/sboms/pkg-1.0.spdx3.json').

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
    sbom_hash = _calculate_record_hash(sbom_bytes)
    sbom_size = len(sbom_bytes)

    with zipfile.ZipFile(wheel_obj, "r") as original_zf:
        dist_info = _find_dist_info_prefix(original_zf, wheel_obj)
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
            sbom_hash,
            sbom_size,
            dist_info,
            stale_arcnames,
        )
        new_record_bytes = new_record_text.encode("utf-8")

        timestamp = _resolve_zip_timestamp(
            record_info.date_time if record_info else None
        )
        _rewrite_wheel_archive(
            wheel_obj,
            original_zf,
            sbom_arcname,
            sbom_bytes,
            record_arcname,
            new_record_bytes,
            timestamp,
            stale_arcnames,
        )

    return wheel_obj, sbom_arcname


def _validate_sbom_filename(filename: str) -> None:
    """Guard against path traversal in an embedded SBOM filename (CWE-22).

    ``filename`` may come from wheel METADATA (untrusted archive content)
    or a user-supplied ``--sbom-basename``, so it must resolve to a plain
    filename with no path separators or traversal segments.
    """
    if not filename or "/" in filename or "\\" in filename or filename in (".", ".."):
        raise ValueError(f"Invalid SBOM filename: {filename!r}")


def _derive_wheel_sbom_filename(zf: zipfile.ZipFile, dist_info: str) -> str:
    """Derive default SBOM filename from wheel METADATA."""
    meta_name: str | None = None
    meta_version: str | None = None
    metadata_path = f"{dist_info}METADATA"
    if metadata_path in zf.namelist():
        content = zf.read(metadata_path).decode("utf-8", errors="replace")
        for line in content.splitlines():
            if line.startswith("Name: ") and not meta_name:
                meta_name = line.split("Name: ", 1)[1].strip()
            elif line.startswith("Version: ") and not meta_version:
                meta_version = line.split("Version: ", 1)[1].strip()
            if meta_name and meta_version:
                break
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
) -> None:
    """Write updated entries to a temporary file and atomically replace target.

    ``stale_arcnames`` are dropped from the rewritten archive rather than
    copied through, so a prior embedded SBOM under a different basename
    does not linger unlisted in the new RECORD.
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

        os.replace(temp_path, wheel_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


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


# pylint: disable=too-many-arguments,too-many-locals,too-many-positional-arguments
def embed_wheel_sbom(
    wheel_path: Path | str,
    *,
    project_dir: Path | str | None = None,
    sbom_path: Path | str | None = None,
    output_path: Path | str | None = None,
    sbom_basename: str | None = None,
    creation_metadata: CreationMetadata | None = None,
    registry: str | Path | IdRegistry | None = None,
    provenance: ProvenanceConfig | None = None,
    enrich: bool | None = None,
    extract_file_header: bool | None = None,
    content_type: bool | None = None,
    content_type_method: str | None = None,
    offline: bool | None = None,
) -> tuple[Path, str, str]:
    """Generate and embed a PEP 770 SBOM into a built Python wheel.

    Args:
        wheel_path: Path to the target .whl file.
        project_dir: Optional source project root containing pyproject.toml.
        sbom_path: Optional path to a pre-generated SBOM to embed directly.
        output_path: Optional path to write a standalone copy of the SBOM.
        sbom_basename: Custom basename for the embedded SBOM file.
        creation_metadata: Optional creation metadata overrides.
        registry: ID registry or path.
        provenance: Metadata provenance config.
        enrich: Override enrichment setting.
        extract_file_header: Override SPDX header extraction.
        content_type: Override content type detection.
        content_type_method: Content type detection method
            ('auto'/'magika'/'extension').
        offline: Offline mode flag.

    Returns:
        Tuple of (modified_wheel_path, embedded_arcname, sbom_json_string).
    """
    wheel_obj = Path(wheel_path).resolve()
    wheel_metadata, _ = read_wheel(wheel_obj)

    if sbom_path is not None:
        sbom_json = Path(sbom_path).read_text(encoding="utf-8")
        eff_basename = sbom_basename
    else:
        proj_root = _resolve_project_root(project_dir)
        if proj_root is not None:
            _, cfg, _ = read_project(proj_root)
            cfg = _apply_config_overrides(
                cfg,
                provenance=provenance,
                enrich=enrich,
                extract_file_header=extract_file_header,
                content_type=content_type,
                content_type_method=content_type_method,
                offline=offline,
            )
            reg = (
                registry
                if isinstance(registry, IdRegistry)
                else IdRegistry.load(proj_root / registry)
                if registry is not None
                else resolve_registry(proj_root, cfg.ids_file)
            )
            sbom_json = _build_sbom_from_project_and_wheel(
                proj_root, wheel_metadata, cfg, reg, creation_metadata
            )
            eff_basename = sbom_basename or cfg.sbom_basename
        else:
            sbom_json = _build_sbom_standalone_wheel(
                wheel_metadata, creation_metadata, registry, provenance, offline
            )
            eff_basename = sbom_basename

    target_filename = f"{eff_basename}{_SPDX3_JSON_EXT}" if eff_basename else None
    res_path, arcname = embed_sbom_in_wheel(
        wheel_obj, sbom_json, sbom_filename=target_filename
    )

    if output_path is not None:
        Path(output_path).write_text(sbom_json, encoding="utf-8")

    return res_path, arcname, sbom_json


def _resolve_project_root(project_dir: Path | str | None) -> Path | None:
    """Resolve project directory if explicitly given or present in cwd."""
    if project_dir is not None:
        candidate = Path(project_dir).resolve()
        if candidate.exists():
            return candidate
    cwd_candidate = Path.cwd()
    for fname in ("pyproject.toml", "setup.cfg", "setup.py"):
        if (cwd_candidate / fname).exists():
            return cwd_candidate
    return None


def _apply_config_overrides(
    cfg: PitloomConfig,
    *,
    provenance: ProvenanceConfig | None,
    enrich: bool | None,
    extract_file_header: bool | None,
    content_type: bool | None,
    content_type_method: str | None,
    offline: bool | None,
) -> PitloomConfig:
    """Apply CLI overrides to PitloomConfig."""
    changes: dict[str, Any] = {}
    if provenance is not None:
        changes["provenance_format"] = provenance.format
        changes["provenance_schema"] = provenance.schema
        changes["provenance_detail"] = provenance.detail
        changes["provenance_preserve_source_metadata"] = (
            provenance.preserve_source_metadata
        )
    if enrich is not None:
        changes["enrich_local"] = enrich
    if extract_file_header is not None:
        changes["extract_file_header"] = extract_file_header
    if content_type is not None:
        changes["content_type_enabled"] = content_type
    if content_type_method is not None:
        if content_type_method not in VALID_CONTENT_TYPE_METHODS:
            raise ValueError(
                "content_type_method must be one of "
                f"{sorted(VALID_CONTENT_TYPE_METHODS)}, got {content_type_method!r}"
            )
        changes["content_type_method"] = content_type_method
    if offline is not None:
        changes["offline"] = offline
    return dataclasses.replace(cfg, **changes)


def _build_sbom_standalone_wheel(
    wheel_metadata: ProjectMetadata,
    creation_metadata: CreationMetadata | None,
    registry: str | Path | IdRegistry | None,
    provenance: ProvenanceConfig | None,
    offline: bool | None,
) -> str:
    """Build SBOM from standalone wheel when no source project dir is present."""
    cwd = Path.cwd()
    reg = (
        registry
        if isinstance(registry, IdRegistry)
        else IdRegistry.load(cwd / registry)
        if registry is not None
        else resolve_registry(cwd, None)
    )
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


__all__ = ["embed_sbom_in_wheel", "embed_wheel_sbom"]
