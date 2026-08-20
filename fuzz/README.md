---
Created: 2026-08-18
Last-Modified: 2026-08-18
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Fuzz harnesses

[Atheris](https://github.com/google/atheris) (coverage-guided, libFuzzer-based)
harnesses for Pitloom's untrusted-input parsing boundaries -- code that
runs on data a user points `loom` at, not on Pitloom's own trusted
config/output.

Two targets, chosen for being the highest-value untrusted-input surfaces
with the lowest harness complexity (pure string-in or single-file-in, no
network, no multi-step state):

- `fuzz_license_expression.py` -- `pitloom.extract._license.normalize_license_expression`.
  By its own contract this never raises for any string input, so the
  harness has no expected-exception allowlist at all: any exception is a bug.
- `fuzz_gguf_header.py` -- `pitloom.extract._gguf.read_gguf`, parsing a
  GGUF AI model file's binary header via the third-party `gguf` package.
  `read_gguf` intentionally converts a `GGUFReader` open failure to
  `ValueError` ("not a valid GGUF file") -- the harness swallows exactly
  that and lets everything else through as a genuine crash signal.

## Platform note

Atheris requires building against a real LLVM Clang with `libFuzzer`
support -- it does not build with Apple Clang (macOS) and has no Windows
wheels. Run this on Linux (matches `.github/workflows/fuzz.yml`, which is
`ubuntu-latest`-only). This is also why `fuzz` is its own
[dependency group](../pyproject.toml), not part of `dev`.

## Running locally

```bash
pip install ".[gguf]" --group fuzz
python fuzz/fuzz_license_expression.py -max_total_time=120
python fuzz/fuzz_gguf_header.py -max_total_time=120
```

`-max_total_time=<seconds>` is a libFuzzer flag Atheris passes through --
without it, fuzzing runs until manually interrupted (Ctrl-C) or a crash
is found. On a crash, Atheris writes a `crash-<hash>` file with the
minimized reproducing input in the current directory; re-run the harness
script with that file as an argument (no flags) to replay it directly
through Python, no fuzzing involved, for debugging.

## Running in CI

`.github/workflows/fuzz.yml` runs both harnesses for a bounded duration
on `workflow_dispatch` (manual trigger) -- see that workflow's own
comments for why this isn't tied to a release-candidate tag. Run it once
before tagging a release, per
[release-checklist.md](../working-docs/implementation/release-checklist.md).

## Adding a new target

Same shape as the existing two: a `_run_one(data: bytes) -> None` helper
containing the actual test logic (importable and callable without
`atheris` installed, so it can be smoke-tested with plain Python or
`pytest` first), a thin `TestOneInput` wrapper, and a `main()` that lazily
imports `atheris` and calls `atheris.Setup`/`atheris.Fuzz()`. Only catch
exceptions in `_run_one` that are the target's own *documented, intentional*
error contract -- letting everything else propagate is the entire point.
