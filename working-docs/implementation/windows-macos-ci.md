---
Created: 2026-09-17
Last-Modified: 2026-10-15
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Real Windows and macOS CI runs

See also: [roadmap.md](../design/roadmap.md) (feature-oriented plan).

**Status (2026-09-17):** shipped on `main` via PR
[#220](https://github.com/bact/pitloom/pull/220).

## What was built

`.github/workflows/test.yml` and `build.yml` each replaced their
ubuntu-only `python-version` matrix with a `strategy.matrix.include:`
list spanning four `{os, python-version}` combinations:
`ubuntu-latest`/3.10, `windows-latest`/3.11, `macos-latest`/3.12 or 3.13
(deliberately different between the two files, to cover more Python
versions across limited CI runners rather than duplicating the same
version on both), and `ubuntu-latest`/3.14 (the coverage-collecting
combo). `test.yml`'s "Run tests" step gained `shell: bash` so its
bash-syntax conditional runs correctly on `windows-latest` (whose
default shell is PowerShell) via Git Bash.

## Why

Pitloom's own `CLAUDE.md` commits to working "seamlessly across
Windows, macOS, and Linux," but CI had only ever run on `ubuntu-latest`.
`--allow-build`'s cross-platform notes (temp-dir handling, path
separators, PR #215's review) were verified only by reasoning, never by
an actual non-Linux run.

## What the first real Windows run found

Adding the `windows-latest` job immediately surfaced 7 real test
failures -- none in production code:

- Several tests in `tests/assemble/test_assemble_ai_metadata.py`,
  `tests/assemble/test_enrich_init.py`, and
  `tests/core/generator/test_generator_file.py` hardcoded a POSIX-only
  absolute path literal (e.g. `"/tmp/pitloom-build-and-read-xyz/..."`)
  to fake `--allow-build`'s `tempfile.mkdtemp()` output. Under Windows
  `pathlib` semantics, `Path(literal).is_absolute()` is `False` for such
  a literal (no drive letter) -- silently skipping the
  absolute-`physical_path` branch each test meant to exercise. A real
  Windows `tempfile.mkdtemp()` value always carries a drive letter and
  is genuinely absolute, so the production code
  (`pitloom.core.project.project_relative_or_fallback()`) was never
  actually broken.
- `tests/extract/lock/test_common.py::test_resolve_pinned_dependencies_abort_policy`
  asserted a hardcoded POSIX-style literal against a log message that
  renders `str(Path(...))` -- which uses native (`\`) separators on
  Windows.
- `tests/assemble/test_embed_core.py::test_embed_sbom_preserves_file_permissions`
  asserted bit-for-bit POSIX permission preservation, which NTFS
  doesn't support (`os.chmod()`/`stat()` there only track a single
  read-only attribute, not owner/group/other bits).

## Decisions made

- **Fixed the test fixtures, not the production code.** Confirmed via
  `PureWindowsPath` that a drive-lettered absolute path (what a real
  `tempfile.mkdtemp()` produces on Windows) already satisfies
  `is_absolute()` correctly; only the *literal test string* was
  unrealistic. Added a shared helper, `fake_build_and_read_path()`
  (`tests/conftest.py`), that builds a genuinely-platform-absolute path
  from the real `tempfile.gettempdir()` at test-run time, and swapped
  it into all 7 call sites.
- **`test_common.py`'s expected string is now derived from the same
  `Path` object** passed into the function under test
  (`f"{lock_file}: ..."`), rather than a second hardcoded literal --
  correct on any OS since both sides render the same way.
- **The permission test spies on `os.chmod` rather than asserting a
  `stat()` effect on Windows.** A stat()-based assertion using an
  always-writable target mode is vacuously true regardless of whether
  the restore call in `src/pitloom/_embed_wheel.py`'s
  `os.chmod(wheel_obj, orig_mode)` actually runs (a freshly-written
  replacement file is writable by default). No black-box check exists
  for this guarantee on Windows, so the test uses
  `unittest.mock.Mock(wraps=os.chmod)` and asserts the spy was called
  once with the expected path and mode -- a deliberate mechanism-level
  check forced by the platform, not a preference for testing internals.

## Related, unrelated fix bundled in the same PR

`pyproject.toml`'s `ai`/`fasttext` extras were split by
`python_version` marker (`fasttext-community` for `<3.14`,
`fasttext==0.9.3` for `>=3.14`), since plain `fasttext==0.9.3` has no
Windows wheel and fails building from source there -- the real-world
bug report that prompted adding Windows CI in the first place. This
left a known, tracked gap: no CI job combined Windows/macOS with
Python 3.14, so that combination's `fasttext==0.9.3` build failure
stayed untested.

**Update (PR #222):** `fasttext-community` 0.11.8 added Python 3.14
wheels, so the marker split is gone -- `fasttext-community>=0.11.8` is
now used unconditionally and the gap above no longer applies.

## Where

- `.github/workflows/test.yml`, `build.yml`: matrix changes.
- `tests/conftest.py`: `fake_build_and_read_path()`.
- `tests/assemble/test_assemble_ai_metadata.py`,
  `tests/assemble/test_enrich_init.py`,
  `tests/core/generator/test_generator_file.py`: call sites.
- `tests/extract/lock/test_common.py`:
  `test_resolve_pinned_dependencies_abort_policy`.
- `tests/assemble/test_embed_core.py`:
  `test_embed_sbom_preserves_file_permissions`.
- `pyproject.toml`, `src/pitloom/extract/ai_model/fasttext.py`,
  `docs/ai-model-formats.md`,
  `examples/sentimentdemo-aibom/{README.md,pyproject.toml}`,
  `working-docs/implementation/model-metadata-extraction.md`: the
  `fasttext`/`fasttext-community` split and its documentation.

## Text-mode newlines in fixtures (PR #305)

`Path.write_text("data\n")` writes `\r\n` on Windows. A test that hashed the
literal `b"data\n"` passed on macOS and Linux and failed on `windows-latest`
only (loom dataset dedup, four cases). Write digest-bearing fixtures with
`write_bytes`. Detail:
[recurring-bug-patterns-platform.md](recurring-bug-patterns-platform.md).
