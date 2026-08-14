---
Created: 2026-08-14
Last-Modified: 2026-08-14
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Post-build wheel embedding (PEP 770): implementation notes

See [docs/cli.md](../../docs/cli.md) and
[docs/github-action.md](../../docs/github-action.md) for the user-facing
command and CI configuration -- this document covers internal design,
ZIP archive manipulation, RECORD formatting, and verification.

See also [hatchling-build-hook.md](hatchling-build-hook.md) for the
Hatchling build-hook counterpart.

## Context and motivation

PEP 770 defines the `.dist-info/sboms/` convention for embedding SBOM
documents into Python wheels (`.whl`). Previously, Pitloom supported
PEP 770 embedding only via its Hatchling build hook
(`pitloom.plugins.hatch`).

However, many Python packages use different build backends
(`flit_core`, `setuptools`, `poetry-core`, `maturin`, `scikit-build-core`),
or build in environments where Python 3.10+ is unavailable at build time.
Because a Python wheel is a standard ZIP archive, post-processing built
wheel files decouples SBOM generation and embedding from the build backend
and Python build version.

## Architecture

Wheel embedding is implemented in `pitloom.embed`:

```text
Built .whl archive (ZIP)
         │
         ├── 1. Locate .dist-info/ prefix (<name>-<version>.dist-info/)
         ├── 2. Assemble / read canonical SPDX 3 JSON-LD (JCS RFC 8785)
         ├── 3. Write to .dist-info/sboms/<name>-<version>.spdx3.json
         ├── 4. Compute SHA-256 base64url hash without padding (PEP 376)
         ├── 5. Update .dist-info/RECORD with new file and retain RECORD,,
         └── 6. Atomically replace .whl (respecting SOURCE_DATE_EPOCH)
```

### RECORD formatting and hash calculation

Under PEP 376 / PEP 427 / PEP 770, each record row is formatted as:

```text
<archive_path>,sha256=<base64url_no_padding>,<byte_size>
```

The SHA-256 digest is encoded in URL-safe base64 with trailing `=`
padding removed:

```python
digest = hashlib.sha256(sbom_bytes).digest()
b64_hash = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
record_entry = f"{sbom_arcname},sha256={b64_hash},{len(sbom_bytes)}"
```

The RECORD file itself is listed as `<dist_info>/RECORD,,`.

### Determinism, atomic writing, and memory efficiency

- `_resolve_zip_timestamp`: Honours the standard `SOURCE_DATE_EPOCH`
  environment variable if set; otherwise reuses the existing `RECORD`
  `date_time` or the current UTC timestamp.
- Atomic replacement: New entries and existing members are written to
  a sibling temporary file (`.whl.tmp`) before calling `os.replace` to
  prevent corrupt archives on process interruption.
- Chunked streaming: Existing zip entries are streamed chunk-by-chunk
  via `shutil.copyfileobj(original_zf.open(info), new_zf.open(info, "w"))`
  rather than loaded into memory, keeping memory consumption minimal even
  for wheels containing large binary files or model weights.

## Authoritative 3rd-party validation

The implementation is verified across two layers:

1. **Wheel & RECORD verification**:
   - **PyPA `installer` (`WheelFile.validate_record()`)**: Authoritative
     reference validator that cryptographically checks every file in the
     wheel archive against `.dist-info/RECORD`.
   - **`check-wheel-contents`**: PyPA wheel linter verifying proper layout
     and directory structure.
   - **`pip install --dry-run`**: Verifies that standard `pip` unpacks and
     installs the wheel cleanly.
2. **SPDX 3 SBOM validation**:
   - **`spdx3-validate`**: Verifies that the embedded SPDX 3 JSON-LD SBOM
     conforms to SPDX 3.0.1 ontology and schema (or any SPDX 3 version
     as specified/detected and agreed with the user's intention at the
     generation time).
