---
Created: 2026-09-30
Last-Modified: 2026-09-30
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# `loom env`: pipdeptree JSON shape

See also: [id-registry-autosync.md](id-registry-autosync.md) (registry claims
for deployed packages); `tests/fixtures/pipdeptree/README.md` (captured
outputs and how they were made); PR #236.

## What was wrong

`extract/env.py` ran `pipdeptree --json-tree --all` (nested nodes
`{key, package_name, installed_version, dependencies: [...]}`), while
`assemble/spdx3/_document_deployed.py` reads `--json`
(`{"package": {...}, "dependencies": [...]}`, flat). Every real package
therefore fell back to name and version `unknown`, dependsOn edges were
lost, and with a registry the claim warning read "registered for both
unknown and unknown". Tests stubbed the `--json` shape by hand, so none
saw it.

## Decisions

- **Extractor runs `--json`.** The assembler already consumed that shape,
  and a flat list gives every installed package once. `--all` is dropped:
  it only affects tree output. `--json` (not `-o json`) is kept because
  both work on the floor (`pipdeptree>=4.2.3`, checked) and `--json` is
  older. `-o json` output is byte-identical.
- **Validate at the boundary.** pipdeptree's output is external data. A
  non-list, a node without a dict `package` carrying a string `key`, a
  non-list `dependencies`, or a dependency without a string `key` raises
  `RuntimeError("Unexpected pipdeptree output: ...")`; so do invalid JSON
  and invalid UTF-8. The CLI reports it as one `ERROR:` line. It is not
  masked as `unknown`. An empty list is a valid, empty environment.
  Stdout is parsed as bytes, so a UTF-8 BOM is accepted.
- **Canonical order at the extractor.** pipdeptree sorts by `key`, but does
  not document it, and `build_deployed()` follows input order (`Package-N`
  numbering, first-claimant-wins registry hits, relationship order). The
  extractor sorts packages by `(key, version, name)` and each package's
  dependencies by `key`. On real output this changes no bytes.
- **Assembler fallbacks left as they are.** `unknown` fallbacks in
  `_document_deployed.py` are now reachable only from a caller passing a
  hand-built tree with no name or version.

## Tests

Real `--json` and `--json-tree` output of an environment built from the
vendored `requests-2.34.2` sdist drives the assembler, determinism,
registry, negative and CLI tests. A live test runs the real extractor on the
test interpreter (no `unknown`; `pytest`'s version matches
`importlib.metadata`).
