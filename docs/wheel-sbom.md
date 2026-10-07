---
Created: 2026-10-07
Last-Modified: 2026-10-07
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Wheel SBOMs and PEP 770 embedding

See also: [Command line](cli.md) for every other subcommand and the common
flags, [Hatchling build hook](hatchling-build-hook.md) and
[GitHub Action](github-action.md) for embedding at build time or in CI, and
[Python API](python-api.md#wheel-embedding-functions) for the same operations
from code.

Commands that read or rewrite built `.whl` files: `loom wheel`,
`embed-wheel`, `verify-wheel` and `validate-wheel`.

## Embed an SBOM (`embed-wheel`)

Generate an SPDX 3 SBOM and embed it in one or more built wheels, writing to
`.dist-info/sboms/` and updating `.dist-info/RECORD`:

```bash
loom embed-wheel dist/*.whl --project-dir .
```

`--project-dir` rescans the source project so the SBOM carries project
metadata (dependencies, licence, AI models). It is never inferred from the
current directory, even when the shell sits in the project root: that
directory may not be the wheel's own project. With it, the file list and
hashes still come from the wheel itself, so they are accurate for any build
backend. Only `--content-type` and `--extract-file-header` can be affected by
the [Source SBOM limitation](cli.md#generate-an-sbom), for a backend on the
Hatchling-based fallback: that per-file enrichment can silently fail to
attach (no data for a file, never wrong data).

Without `--project-dir` (and without `--sbom`), `embed-wheel` embeds a
standalone-wheel SBOM built from the wheel's own contents: no project scan,
so no AI-model enrichment and no `[tool.pitloom]` beyond an explicit
`--config`. AI models inside the wheel are still found (see
`--scan-model-usage`):

```bash
loom embed-wheel dist/mypackage-1.0.0-py3-none-any.whl
```

Or embed an existing SBOM:

```bash
loom embed-wheel dist/*.whl --sbom sbom.spdx3.json
```

The SBOM's declared subject name/version (PEP 503/440-normalised) is checked
against the wheel's own `.dist-info/METADATA` *before* anything is written. A
mismatch is an `ERROR:` that aborts the embed (exit 1, nothing written);
`--allow-mismatch` downgrades it to a `WARNING:` and embeds anyway (for
best-effort CI). A Pitloom-generated SBOM (no `--sbom`) is never checked: it
is built from the same metadata. An external SBOM is embedded verbatim and may
list `.dist-info` files.

Or use `--embed` on `loom wheel`:

```bash
loom wheel dist/mypackage-1.0.0-py3-none-any.whl --embed
```

It embeds the same kind of SBOM as `embed-wheel`: RFC 8785 canonical JSON, no
relationship descriptions, no registry update. So `--pretty`,
`--describe-relationship` and `--update-id-registry` warn and have no effect,
and `-o FILE` writes a copy of exactly what was embedded.

Other flags:

- `--sbom-basename NAME` sets the embedded file's basename. A trailing
  `.spdx3.json` is optional and dropped with a `WARNING:`. The default is
  `<name>-<version>.spdx3.json` from the wheel's own name/version, with a
  control character, whitespace, `/`, `\` or `:` becoming `_`; with no name or
  version in `METADATA`, or a name over 255 characters, the wheel's
  `.dist-info` directory name (escaped the same way) is used.
- `-o`/`--output` names the modified wheel and is an `ERROR:` with more than
  one wheel (ambiguous). Omit it to modify each wheel in place.
- `--verify`/`--validate` run the checks below on the wheel just embedded. A
  failure is reported and sets the exit code, but the embed is not rolled
  back.

```bash
loom embed-wheel dist/*.whl --project-dir . --verify --validate
```

### What an SBOM lists

Every wheel-reading command (`loom wheel`, `generate <whl>`, `embed-wheel`,
`wheel --embed`) lists the wheel's payload only: nothing under the wheel's own
`.dist-info` (`METADATA`, `WHEEL`, `RECORD`, `licenses/`, `sboms/`,
signatures). An SBOM describes the packaged project, not its container, so a
listed hash never goes stale when the embed rewrites `RECORD` and adds
`sboms/`. The Hatchling hook and `loom project` list no
`.dist-info/licenses/*` file either.

A wheel's own `.dist-info` is the top-level directory its file name names
(PEP 503/440 comparison). Where the file name names none, it is the only
top-level `.dist-info`, with a `WARNING:` if the file name is a wheel name. A
`.dist-info` vendored deeper in the tree is never the wheel's own. With none,
or several not picked out by the file name, `loom wheel` and `loom generate`
warn and name the package `unknown`; `wheel --embed`, `embed-wheel`,
`verify-wheel` and `validate-wheel` refuse the wheel. `METADATA` is read for
its headers only (at most 16 MiB and 10,000 headers); past a cap, one
`WARNING:` per command and the name is `unknown`.

### Signed wheels

**SECURITY:** a wheel with a `RECORD` signature (`RECORD.jws`, `RECORD.p7s`)
is refused, and left untouched, by `embed-wheel` and `wheel --embed`: the
embed rewrites `RECORD`, so the signature would stop verifying.
`--allow-signed-wheel` removes the signature files and embeds (one `INFO:` per
file); re-sign afterwards. Like `--allow-build`, it has no `[tool.pitloom]`
equivalent: it is a per-run decision.

Pitloom sees only signatures inside the wheel. Any embed changes the wheel
file's own digest, so a signature or attestation over the file (detached GPG
`.asc`, Sigstore bundle, PEP 740 attestation) and a recorded wheel hash (lock
file, `pip --hash`) stop matching, and Pitloom cannot detect them. Embed
first, then sign, attest, upload and hash.

### Refused archives

`loom wheel`, `generate`, `wheel --embed` and `embed-wheel` read every member.
They refuse a file that is not a ZIP, and a wheel with a member that cannot be
read (damaged, encrypted, a name that is not UTF-8), with one name twice (also
as `a/M` and `a\M`), or with a NUL in a name (`zipfile` cuts it there, so an
installer extracts it under another member's name). `wheel --embed` and
`embed-wheel` also refuse a wheel whose own `.dist-info` has a non-conforming
member name.

`verify-wheel` reads only the member names, the own `.dist-info`'s `METADATA`
and the embedded SBOM; `validate-wheel` only the names and the embedded SBOM.
A damaged other member does not fail them, but a damaged member they read, a
duplicate or NUL name, or a file `zipfile` cannot open does.

Each refusal is one `ERROR:` naming the archive and, where there is one, the
member; exit 1, nothing written (not even the `-o` copy). With several wheels
the others are still processed. The library raises `ValueError`.

## Verify (`verify-wheel`)

Check that a wheel's embedded SBOM is at the PEP 770 location
(`.dist-info/sboms/`), uses its format's recommended extension, and declares a
subject name/version matching the wheel's own `.dist-info/METADATA`:

```bash
loom verify-wheel dist/*.whl
loom verify-wheel dist/mypackage-1.0.0-py3-none-any.whl --sbom-filename mypackage-1.0.0.spdx3.json
loom verify-wheel dist/*.whl --fail-on-mismatch
```

- A missing SBOM is an `ERROR:` (exit 1).
- A non-conventional extension is a `WARNING:` only (exit 0).
- Several `sboms/` entries need `--sbom-filename` to pick one, else `ERROR:`.
- A name/version mismatch is a `WARNING:` (exit 0); `--fail-on-mismatch` makes
  it an `ERROR:` (exit 1).
- If the subject name/version cannot be extracted at all (unsupported format,
  or SPDX 3 with an unexpected graph shape), the cross-check is skipped with a
  `WARNING:` naming why, regardless of `--fail-on-mismatch`.

## Validate (`validate-wheel`)

Validate the embedded SBOM's content against its format's schema and SHACL
rules (SPDX 3 JSON-LD only, via the `spdx3-validate` library also behind
[`loom fragment validate`](fragments.md#validate-fragments); needs `pip
install "pitloom[validate]"`):

```bash
loom validate-wheel dist/*.whl
```

An embedded file in an unrecognised format prints a `WARNING:` and skips
validation (exit 0): unsupported is not invalid.

## Package hash

The package element's `verifiedUsing` holds a SHA-256 Merkle root over the
wheel's payload. What it covers follows the SBOM type:

- **Analyzed** (`loom wheel`, `generate <whl>`, `embed-wheel` without a
  project directory, `wheel --embed`): the wheel as built.
- **Source** (`loom project`) and the **Build** SBOM of the Hatchling hook:
  the source files the build backend selects, hashed before the build. When
  the build adds payload of its own (shared data, scripts, generated or
  repaired files) the root differs from the built wheel's, as the two describe
  different things.
- **Build** with `embed-wheel --project-dir`: the wheel as built, so it can
  differ from the hook's root for the same wheel.

A wheel's `<name>-<version>.data/` directory (PEP 427: files installed outside
`site-packages`, such as `scripts/`, `data/` and `headers/`) is payload, not
packaging metadata. It is listed and hashed under its path in the wheel, e.g.
`demo-1.0.data/data/share/demo/d.txt`, not its install destination. The hook
and `loom project` cannot see it before the build, one reason their root
differs from the built wheel's.

To recompute the root of a built wheel:

1. Take every wheel member except those under the wheel's own `.dist-info`
   (the top-level directory its file name names, compared per PEP 503 names and
   PEP 440 versions). Another `*.dist-info` deeper in the tree is payload.
   Directory entries are not members.
2. Name each by its install-location path (POSIX, normalised). A member name
   that is not one (`\`, `./`, `//`, `..`, an absolute path) is normalised or
   skipped by Pitloom, each with a `WARNING:`; the snippet below reads names as
   stored, so it reproduces the root of a conforming wheel only.
3. Sort by that path (Python `sorted`, code-point order).
4. A leaf is the raw 32-byte SHA-256 of the member's bytes.
5. Combine adjacent pairs as `sha256(left || right)`; an odd last node is
   promoted unchanged; repeat until one node remains.
6. The root is that node in lowercase hex. A single file's root is its own
   digest; an empty payload has no hash.

A wheel with no single own `.dist-info` has none to leave out: `loom wheel`
lists and hashes every member, and the embed commands refuse it. SBOM
relationships and directory elements are not part of the root.

```python
import hashlib
import zipfile


def package_hash(wheel: str, own_dist_info: str) -> str | None:
    leaves = {}
    with zipfile.ZipFile(wheel) as zf:
        for name in zf.namelist():
            if name.endswith("/") or name.split("/")[0] == own_dist_info:
                continue
            leaves[name] = hashlib.sha256(zf.read(name)).digest()
    level = [leaves[name] for name in sorted(leaves)]
    if not level:
        return None
    while len(level) > 1:
        nxt = [
            hashlib.sha256(level[i] + level[i + 1]).digest()
            for i in range(0, len(level) - 1, 2)
        ]
        if len(level) % 2:
            nxt.append(level[-1])
        level = nxt
    return level[0].hex()


print(package_hash("pkg-1.0-py3-none-any.whl", "pkg-1.0.dist-info"))
```
