---
Created: 2026-10-29
Last-Modified: 2026-10-29
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Embed an SBOM into a wheel (PEP 770): the forms and what they do

See also: `../SKILL.md` ("Embed an SBOM into a wheel (PEP 770)", which holds
the rules: `--project-dir`, the signed-wheel check and the question before
`--allow-signed-wheel`); [known-limitations.md](known-limitations.md)
("Signed wheels: what to tell the user", "Refused wheels and unknown
identity"); [examples.md](examples.md).

For a request to *embed* an SBOM into a built wheel rather than write it as a
standalone file -- PEP 770's `.dist-info/sboms/` convention -- use
`embed-wheel` instead of `wheel`:

```bash
# standalone: no project scan
loom embed-wheel dist/mypackage-1.0.0-py3-none-any.whl
# multiple wheels, Build SBOM
loom embed-wheel dist/*.whl --project-dir .
```

`--project-dir` is required to have `embed-wheel` rescan the source
project (never inferred from the current directory) -- pass it whenever
the user has a project directory to scan; omit it only for a genuinely
standalone wheel. `embed-wheel` also accepts `--allow-build` (see
"Choosing `--build-timeout`" in `../SKILL.md`).

Or embed an already-generated SBOM file directly -- its declared subject
name/version is cross-checked against the wheel's own METADATA first; a
mismatch aborts the embed (`--allow-mismatch` downgrades to a warning). The
SBOM is embedded verbatim, so one from another tool may list files Pitloom's
own never do:

```bash
loom embed-wheel dist/*.whl --sbom sbom.spdx3.json
```

Or embed directly on `loom wheel` for a single wheel's own Analyzed SBOM
(no project-directory scanning):

```bash
loom wheel dist/mypackage-1.0.0-py3-none-any.whl --embed
```

`embed-wheel` mutates the `.whl` archive in place and works on any wheel
regardless of build backend, unlike the Hatchling-specific build hook. It
rewrites `RECORD` (the SBOM's row added or updated, rows of an earlier
Pitloom SBOM it replaces dropped) and writes the SBOM under
`.dist-info/sboms/`. Pitloom's wheel SBOMs list the payload only (nothing
under the wheel's own `.dist-info`), so every listed hash matches the final
wheel. Full flags, including `--output` (rejected when more than one wheel
matches) and `--sbom-basename` (a name without extension; a trailing
`.spdx3.json` is dropped with a `WARNING:`):
<https://bact.github.io/pitloom/wheel-sbom/>.

## Check the embedded SBOM in the same command

To check the wheel's embedded SBOM right after this same embed, pass
`--verify`/`--validate` to `embed-wheel` itself -- both checks share the
one disk read this embed already did:

```bash
loom embed-wheel dist/*.whl --project-dir . --verify --validate
```

A pass adds no line; a failure prints `ERROR:` lines and exits 1, after the
wheel was rewritten; an SPDX 3 `--sbom FILE` that fails validation is
refused first. For checking an already-embedded wheel later, use the
`sbom-validate` skill ("Validate a wheel's embedded SBOM").
