---
Created: 2026-08-14
Last-Modified: 2026-10-03
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
Hatchling build-hook counterpart, and
[archive-member-names.md](archive-member-names.md) for how wheel member names
become `software_File` names.

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

## What a wheel SBOM lists, and signed wheels (#269)

- **One rule: an SBOM describes the packaged project, not the package.**
  `extract.wheel.read_wheel()` drops every member under the wheel's own
  `.dist-info` (METADATA, WHEEL, RECORD, `licenses/`, `sboms/`, signatures), so
  `loom wheel`, `generate <whl>`, `embed-wheel` and `wheel --embed` list the
  payload only. `RECORD` is rewritten by the embed and `sboms/` cannot hold its
  own hash, so both went stale; the rest is build output the hook never lists.
  The build hook and `loom project` list no `.dist-info/licenses/*` either: a
  file link to that path means nothing in another package format. Licence
  information stays at package level. Pitloom never wrote `licenses/` (the
  backend does) and an embed copies it unchanged.
- **Package Merkle root over the payload, on every wheel surface.** Before,
  only the hook, `loom project` and `embed-wheel --project-dir` carried one.
  The wheel surfaces share `merkle_root_of_files`; `get_wheel_files()` keeps
  its own computation over a source tree, and a test asserts the two agree
  (a drift guard, not a refactor). What a root covers follows the SBOM type:
  Analyzed (`loom wheel`, standalone embed) the wheel as built; Source and the
  hook's Build the pre-build source walk, so they differ when the build adds
  payload (expected). `embed-wheel --project-dir` is Build but hashes the wheel
  as built: the one pair left open (roadmap). A wheel's `.data/` directory is
  payload (listed and hashed under its wheel path, not its install
  destination); only the own `.dist-info` is excluded. The recompute procedure
  is in `docs/cli.md`.
- **Signed wheels are refused.** `RECORD.jws`/`RECORD.p7s` sign the `RECORD`
  the embed rewrites. Keeping them leaves a signature that fails to verify
  (worse than none); silently dropping loses trust data. Default is a
  refusal before any write; `--allow-signed-wheel` (CLI, Action, library
  `allow_signed_wheel=`) removes them with one `INFO:` each. No
  `[tool.pitloom]` key, like `--allow-build`: a committed key would permit
  removal on every run and every later signed release.
- **External signatures are undetectable.** Any embed changes the wheel
  file's digest, so a detached GPG `.asc`, Sigstore bundle, PEP 740
  attestation or recorded hash (lock file, `--hash`) stops matching. Documented
  rule: embed first, then sign, attest, upload, hash. No runtime text: nothing
  to detect.
- **Rejected:** keeping `licenses/` in the listing (file link meaningless for
  other formats); a root over every listed file (the root would then depend on
  what an SBOM lists); `loom wheel` listing every member (one rule on all
  surfaces); a `[tool.pitloom]` key for `--allow-signed-wheel` (ambient
  consent); warning instead of refusing; a root on only some surfaces.

### Behaviour matrix (measured at 81ae226f)

A project built with the Hatchling hook: `license = "MIT"`,
`license-files = ["LICENSE"]`, two modules, and
`[tool.hatch.build.targets.wheel.shared-data] "share" = "share/demo"` (so the
build adds `demopkg-1.0.data/data/share/demo/d.txt`). The same wheel went
through every surface, each on a fresh copy. The hook's SBOM was read from the
wheel; `loom project` ran on the source tree. The repo's `.venv` `loom` was
used, `--offline`.

| Member / property | Hook | `loom project` | `loom wheel`, `generate <whl>` | Standalone embed | `wheel --embed` | `embed-wheel --project-dir` |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| SBOM type | Build | Source | Analyzed | Analyzed | Analyzed | Build |
| `demopkg/__init__.py`, `b.py` | listed | listed | listed | listed | listed | listed |
| `.data/.../d.txt` (build-added) | not listed (source walk) | not listed | listed | listed | listed | listed |
| `.dist-info/licenses/LICENSE` | not listed | not listed | not listed | not listed | not listed | not listed |
| `METADATA`, `WHEEL`, `RECORD`, `sboms/*`, signatures | not listed | not listed | not listed | not listed | not listed | not listed |
| Directory elements for `.dist-info/...` | none | none | none | none | none | none |
| `hasDeclaredLicense` source | package only | package only | package only | package only | package only | package only |
| Package Merkle root | `aea983240d` | `aea983240d` | `44f76c7537` | `44f76c7537` | `44f76c7537` | `44f76c7537` |

What the table shows:

- No surface lists anything under the own `.dist-info`, or links to it; the
  only licence statement is on the package.
- Every surface that reads the built wheel gives one file list and one root.
  The hook and `loom project` give another root, the same one, because they
  hash the source walk before the build and cannot see the `.data/` member
  (expected by SBOM type; documented in `docs/cli.md`).
- The one pair that does not follow the type rule is the two Build SBOMs: the
  hook (`aea983...`) and `embed-wheel --project-dir` (`44f765...`). Open, see
  the roadmap.

Before the change (0.19.0), from the issue and the code, not re-run: a wheel
embed listed `RECORD`, `METADATA`, `WHEEL`, `licenses/LICENSE` and any earlier
`sboms/*` with hashes taken before the embed (`RECORD` and `sboms/*` stale);
`loom wheel` listed every member; the hook and `loom project` listed
`licenses/LICENSE` linked to the declared licence; only the hook, `loom project`
and `embed-wheel --project-dir` carried a package root; signatures were
removed silently.

Signed wheel, same project with `RECORD.jws` and `RECORD.p7s` added:

| Command | Result |
| :--- | :--- |
| `embed-wheel` or `wheel --embed`, no flag | exit 1, one `ERROR:` naming the signature and the flag, wheel byte-identical |
| `embed-wheel --allow-signed-wheel` | exit 0, both signatures removed from archive and `RECORD`, one `INFO:` each, `validate_record()` passes, licence file bytes unchanged |
| `loom wheel --allow-signed-wheel` (no `--embed`) | one `WARNING: Options: ...: --allow-signed-wheel has no effect without --embed` |

To reproduce: build the project with `pip wheel . --no-build-isolation
--no-deps`, then run `loom wheel`, `generate`, `project`, `embed-wheel`
(with and without `--project-dir`) and `wheel --embed` on copies, and compare
`software_File` names and the package `verifiedUsing`. Independent recompute:
`docs/cli.md`, "Recomputing the package hash".

