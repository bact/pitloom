---
Created: 2026-10-15
Last-Modified: 2026-10-29
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# AI model scan lessons: runtime and output

See also: [ai-model-scan-security-lessons.md](ai-model-scan-security-lessons.md)
(the entry page: setting, how the problems were found, principles),
[ai-model-scan-security-lessons-parsers-and-archives.md](ai-model-scan-security-lessons-parsers-and-archives.md)
(sections 3.1-3.3),
[ai-model-scan-security-lessons-transparency-and-correctness.md](ai-model-scan-security-lessons-transparency-and-correctness.md)
(sections 3.7-3.10).

## 3.4 Python runtime surprises

- **A dict never shrinks.** Cutting a 1.5M-entry map to 1000 by deleting
  keys keeps the 1.5M-slot table: 24 such models in one wheel peaked at
  5.8 GB. Rebuilding a new dict of the kept entries: 0.58 GB. A cap that
  bounds the output did not bound memory.
- **Building a "dropped keys" set costs as much as the map**: the first fix
  raised the one-model peak by 350 MB. Collect the kept keys instead.
- **`contextlib.redirect_stderr` is process-wide.** Two threads capturing
  fickling's stderr could leave `sys.stderr` swapped for good, after which
  every warning vanished. Replaced by one per-thread-routing proxy.
- **`KeyboardInterrupt` can land anywhere**, including between registering
  state and entering `try`, leaving a thread's stderr swallowed. Register
  inside `try`; undo by object identity.
- **CPython 3.14 can leak a lock**: an interrupt can arrive after
  `Lock.__enter__` acquired it and before the protected block starts
  (171 of 734 injected interrupts on 3.14.7; none on 3.10-3.13). A "retry
  the undo until it succeeds" loop then hung beyond Ctrl-C. Bound every
  retry, and take locks with a timeout.
- **`int()` of long decimal text is quadratic** when the digit limit is off
  (`PYTHONINTMAXSTRDIGITS=0`, or CPython 3.10.0-3.10.6): `pickletools`
  converts `INT`/`LONG` arguments with it; 1M digits took 3.4 s, about
  4 min extrapolated at an 8 MiB pickle (0.034 s at 100k digits). Do not
  let a decoder convert numbers you do not need. Fixed: the pre-walk is now
  Pitloom's own (`formats/pickle_walk.py`, over `pickletools.opcodes`), which
  finds a decimal argument with a bounded `readline(4303)` and never
  converts it; a 1M-digit `LONG` is refused in about 25 microseconds with
  the limit off, and 8 MiB of 4300-digit `INT`s (1949 opcodes) is walked in
  4.5 ms where `genops` took 127 ms.
- **The outcome depended on the interpreter's configuration.** With the
  default `int_max_str_digits` a number over 4300 digits made `genops`
  raise, reported as a malformed pickle; with `PYTHONINTMAXSTRDIGITS=0`
  (or an older patch level) the same file was accepted, slowly. The bound
  must not vary with the environment, so the cap is a property of the
  input: 4300 digits, counted the way CPython counts them (sign, `L` and
  whitespace excluded). Residue: a limit set *lower* than the default
  (e.g. `PYTHONINTMAXSTRDIGITS=640`) still makes fickling fail on a
  1000-digit number, a warning where the default gives none, and the type
  of model is then lost (a pickle whose top-level class takes such a number
  gives different SBOM bytes). Python 3.12 and later convert big numbers far faster
  (`genops` on 1M digits: 0.39 s on 3.14 against about 3.4 s on 3.10), so the
  regression test bounds the bytes read, not the time.
- **A byte cap is not a digit cap.** The first plan capped the argument at
  4302 bytes on the belief that everything shorter converts under the
  default limit. False: a 4301-digit unsigned `INT` (4301 bytes) and a
  4301-digit `LONG` (`...L`, 4302 bytes) fit in 4302 bytes and CPython
  still rejects them. The cap counts digits; the 4302-byte window only
  bounds the scan.
- **Python 3.14 differences surfaced in CI**: `compression.zstd` raises its
  own `ZstdError` for zip method 93; `Path.exists()` no longer raises
  `PermissionError`.
- **Test isolation of global logging.** A logging handler bound to the
  `sys.stderr` of the moment captured pytest's per-test capture stream;
  once that closed, a later test on the same xdist worker got `--- Logging
  error ---` on stderr. It failed one CI leg and 1 in 10 local runs, by
  test order only. Restore the logger's handlers after every test.
- **`pickletools.genops` is a decoder, not an unpickler**: it never
  constructs objects or calls `find_class`, so it is safe to walk opcodes
  of a hostile pickle within an opcode cap, but not before the decimal
  conversions above are bounded.

## 3.5 Logs and terminals are an output channel

- **Log injection.** Archive member names and reader exception text reach
  stderr. A name containing a newline, `::error::` (a GitHub Actions
  workflow command) or U+202E (bidi override) could forge lines or
  commands. Every untrusted string goes through one escaping helper; a
  multi-line exception collapses to one tagged line.
- **Third-party libraries print.** fickling wrote 62 MB to stderr for one
  file; captured into a bounded sink and summarised in one warning.
- **No temp paths in logs or SBOMs.** Exception text names the temporary
  copy; it is scrubbed back to the member's name in every spelling (as
  given, resolved, `repr`-escaped, forward slashes).
- **Truncate before escaping**, or the escaped quote loses its closing
  delimiter.
- **The SBOM's own provenance is an output channel too.** Provenance
  strings are parsed back (`Source: x | Field: y`), and a key read from a
  model, an archive member or a file name holding `|` forged a segment that
  a merge or the `minimal` filter then acted on. Every AI-model reader now
  builds them through one sanitising builder, held by a lint (#389). See
  [provenance-injection-and-message-contract.md](sbom-generator-field-notes/provenance-injection-and-message-contract.md).

## 3.6 Determinism (an SBOM requirement, not a nicety)

- **A cap picks a subset, so the subset's order must be stable.** The
  Safetensors library returns `__metadata__` from a Rust hash map whose
  order differs per process; with "keep the first 1000", every run kept a
  different 1000 (3 runs, 3 different SBOMs). Fixed by keeping the
  smallest keys in key order (`heapq.nsmallest`, no full sort). Survey
  every reader's source order: file order is stable, hash-map order is not.
- **Fixing determinism broke correctness** (round 5b): cutting the map
  before looking up well-known keys (`modelspec.title`, `version`) lost
  the model's name. Cut only what is kept as bulk properties.
- **Different settings give different SBOMs, by design** (trust flag,
  ceiling, caps, usage scan, build-and-read). Same input plus same
  settings must give identical bytes; every setting that changes the
  output is documented and announced.
- **Archive member order leaked into ids** (wheel-identity PR): wheel
  files were listed in archive order and `File-N` ids are minted in list
  order, so the same files zipped in another order gave another SBOM.
  Sorting by install path fixed it; any reader of an archive needs this
  check. The sdist reader has the same fault, confirmed: the same five
  files in reverse tar order gave `PKG-INFO` `File-2` in one SBOM and
  `File-7` in the other (open; see
  [id-registry-followups.md](../design/id-registry-followups.md)).
