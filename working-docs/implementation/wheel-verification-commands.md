---
Created: 2026-08-20
Last-Modified: 2026-09-01
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# `verify-wheel` / `validate-wheel`

See also: [roadmap.md](../design/roadmap.md) (Near-term -- "PEP 770 /
embed-wheel"), [wheel-sbom-verification.md](wheel-sbom-verification.md)
(per-release manual verification records these commands automate).

## `loom verify-wheel` / `loom validate-wheel` ([PR #202](https://github.com/bact/pitloom/pull/202))

Check that a wheel's embedded SBOM is at the correct
`.dist-info/sboms/<basename>` location and, separately, passes
schema/SHACL validation. Shipped as two flat subcommands rather than a
single `--verify` flag originally sketched: `verify-wheel` (structural,
format-neutral -- location + recommended-extension check) and
`validate-wheel` (content, SPDX3-only today -- schema/SHACL via
`spdx3-validate`'s library API), reusing
`pitloom._wheel_sbom_location.find_embedded_sbom()` for the shared
location logic and `pitloom.cli.commands.utils._validate_spdx3_documents()`
(also now backing `pitloom fragment validate`) for the shared validation
path. `embed-wheel` gained `--verify`/`--validate` convenience flags
that run the same checks against the wheel just embedded, mirroring how
`wheel --embed` already chains into a shared function rather than
duplicating logic. Replaces `.github/workflows/pypi-publish.yml`'s
hand-rolled bash `unzip -Z1` + glob-match location check and its
separate `spdx3-validate --json` shell-out.

## `verify-wheel` name/version cross-check

An embedded SBOM's declared subject `name`/`software_packageVersion`
(SPDX3 JSON-LD only) is cross-checked against the wheel's own
`.dist-info/METADATA` `Name`/`Version`, PEP 503/440-normalized. Lives
in `verify-wheel` (`src/pitloom/cli/commands/verify_wheel.py`) rather
than `embed_wheel_sbom`, since it covers every embedding path, not
just `--sbom`-supplied SBOMs. Default severity `WARNING:` (exit 0);
`--fail-on-mismatch` makes it `ERROR:` (exit 1). Shared helpers:
`read_wheel_name_version` (`src/pitloom/_wheel_sbom_location.py`, also
now used by `_derive_wheel_sbom_filename`,
`src/pitloom/_embed_wheel.py:149-166`, replacing its previously-inlined
METADATA parse), `extract_spdx3_subject_identity`, and
`check_spdx3_name_version` (both `src/pitloom/_sbom_format.py`).

## `embed-wheel --sbom` pre-embed name/version enforcement

Building on the `verify-wheel` cross-check above (which only catches a
mismatch post-hoc, and only if someone runs it), `embed_wheel_sbom()`
(`src/pitloom/embed.py`, `_enforce_sbom_name_version`) cross-checks an
externally-supplied `--sbom`'s declared name/version against the
target wheel's own METADATA *before* anything is written. A mismatch
raises `ValueError` and aborts the embed (exit 1, nothing written) by
default; `--allow-mismatch` downgrades it to `WARNING:` and embeds
anyway (CI/best-effort use case). A Pitloom-generated SBOM (no
`--sbom`) is never checked -- it's built from the same wheel metadata,
so it can't diverge. `embed-wheel --verify` was also fixed to actually
run the name/version check (it previously called `_check_location`
directly, bypassing it entirely) -- always non-fatal there, matching
`--verify`'s existing severity contract.
