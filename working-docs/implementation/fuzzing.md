---
Created: 2026-08-18
Last-Modified: 2026-08-18
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Fuzzing: scope and trigger decisions

Implements OpenSSF Best Practices' `dynamic_analysis` (SUGGESTED): "at
least one dynamic analysis tool be applied to any proposed major
production release ... before its release." See `fuzz/README.md` for
how to actually run the harnesses this doc explains the *why* behind.

## Scope: two targets, not more

Pitloom has several untrusted-input parsing boundaries (AI model file
formats, license expressions, `pyproject.toml`/`setup.cfg` parsing,
wheel/zip archive contents). Fuzzing all of them would be the most
thorough option, but harness-writing and triage time scale with target
count, and this is a SUGGESTED (not MUST) criterion for a
single-maintainer project. Scoped to the two highest-value, lowest-harness-complexity
targets:

- **License expression normalization**
  (`pitloom.extract._license.normalize_license_expression`) -- pure
  string in, string out, no filesystem/network. By its own contract it
  never raises for any input, so the harness needs no expected-exception
  allowlist at all -- the simplest possible target.
- **GGUF header parsing** (`pitloom.extract._gguf.read_gguf`) --
  represents the AI-model-file parsing surface as a whole (GGUF, ONNX,
  Safetensors, etc. all share the same "arbitrary binary file the user
  points `loom model` at" threat model); GGUF was picked over the
  others because it required no fuzz-harness-side work to reach the
  interesting code (`GGUFReader` takes a bare file path, no wrapping
  container format to construct first, unlike e.g. Safetensors' header
  framing or a wheel's ZIP structure).

Other parsers remain candidates for a future scope expansion but aren't
in it now -- see `fuzz/README.md`'s "Adding a new target" for the shape
a new harness should take if one gets added later.

## Trigger: manual `workflow_dispatch`, not an RC tag

Considered gating the fuzz workflow on pushing a release-candidate tag
(e.g. `v2.5-rc1`), mirroring how some larger projects (CPython, curl)
run extra scrutiny against RCs before promoting them. Went with a plain
manual `workflow_dispatch` trigger instead, run as a release-checklist
step before tagging, because:

- Pitloom's release process
  ([release-checklist.md](release-checklist.md)) has no RC concept
  today -- it tags and publishes directly. Introducing an RC-tag
  convention (a second tag, a "did the RC's fuzz run finish and come
  back clean" bookkeeping step, PyPI pre-release version handling)
  would exist solely to give the fuzzer a trigger, not to serve any
  other need.
- A time-bounded manual run (`-max_total_time=<seconds>` via the
  workflow's `duration_seconds` input) gives a predictable answer
  before tagging, rather than depending on however long an RC window
  happens to stay open.
- It's simpler to keep straight later: "did I run the fuzz workflow
  before this release" is one checklist line, not a two-tag state
  machine.

If Pitloom starts cutting RCs for other reasons in the future, adding
`v*-rc*` as an additional trigger alongside `workflow_dispatch` is a
small change to `.github/workflows/fuzz.yml` at that point -- not
worth building preemptively now.

## First run found a real bug

Before any CI wiring existed, a 50-iteration hand-picked probe plus a
short random-bytes smoke pass (plain Python, not Atheris -- Atheris
itself doesn't build on this maintainer's macOS dev machine; see
`fuzz/README.md`'s platform note) against the license-expression
harness found a genuine crash within seconds: a lone `)` (and several
related unbalanced-paren shapes) made the third-party `py-spdx-license`
parser raise `IndexError` from deep in its own parser-stack reduction
logic, instead of its documented `ParseError`. `normalize_license_expression`
only caught `ParseError`, so the `IndexError` escaped, breaking the
function's own "never raises" contract.

Fixed in `pitloom.extract._license.normalize_license_expression` by
widening the except clause to also catch the generic case (matching the
same defensive pattern its sibling `canonicalize_license_id` already
used for its own third-party call), with a regression test in
`tests/assemble/test_license_normalization.py`
(`test_normalize_license_expression_unbalanced_close_paren_falls_back`).
The underlying bug belongs to `py-spdx-license` upstream, not Pitloom --
this fix is a defensive boundary, not a claim that Pitloom's own logic
was wrong.
