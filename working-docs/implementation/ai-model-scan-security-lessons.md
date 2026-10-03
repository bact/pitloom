---
Created: 2026-10-01
Last-Modified: 2026-10-02
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Lessons from scanning AI models in untrusted packages

See also: [ai-model-scanning.md](ai-model-scanning.md) (the design as
built), [model-metadata-readers.md](../design/model-metadata-readers.md)
(the planned header-only readers), `docs/ai-model-scan-limits.md` (the
user-facing caps).
See also: [SBOM generator field notes](sbom-generator-field-notes/README.md).

Experience notes from PR #263 (scan AI models inside built wheels), written
as raw material for a paper on building an SBOM generator for AI artefacts.
Every number below was measured (peak resident memory under a watchdog,
macOS, CPython 3.10 unless stated); "PLAUSIBLE" findings are left out.

## 1. Setting

- Pitloom generates SPDX 3 SBOMs for Python packages, including the AI
  models they ship (`ai_AIPackage` elements with format, hyperparameters,
  inputs/outputs). Before #263 only a project directory was scanned; #263
  added scanning inside built wheels.
- **Threat model change.** A project directory is usually the user's own
  tree. A wheel is often someone else's: a dependency, a download, a pull
  request artefact in CI. The SBOM generator becomes a parser of hostile
  input, run automatically, often in CI with no human watching.
- **The core tension.** An SBOM wants as much metadata as possible; every
  extra field read is attack surface. Model formats are designed for
  loading, not inspection, and their libraries parse (or load) far more
  than an SBOM needs.
- Formats involved: GGUF, ONNX, PyTorch (`.pt` pickle and zip, PT2),
  Safetensors, Keras (v3 zip, legacy HDF5), NumPy (`.npy`, `.npz`),
  fastText.

## 2. How the problems were found

Nine review rounds over the one PR, each by a separate AI reviewer agent
(Claude Opus) with a fresh context, fixes by another agent (Claude Sonnet),
coordination and design decisions by a third, decisions confirmed by the
human maintainer:

| Round | Scope | Notable outcome |
|---|---|---|
| 1-2 | PR, security | Native-library crashes/hangs, decompression bombs, log injection, aggregate size |
| 3 | fixes of round 2 | GGUF bound bypassed three ways; stderr race |
| 4 | fixes of round 3 | Python dict memory never released |
| 5a | fixes of round 4 only | Non-determinism from a Rust hash map; Python 3.14 hang |
| 5b | whole PR, fresh reviewer | A fix of 5a lost model names; ZIP central-directory bomb |
| 5c | fixes of 5b only | Our own ZIP pre-check disagreed with `zipfile` three ways |
| 6 | whole PR | `.pth` path-config files taken for PyTorch models; DEBUG names unescaped |
| 7 | surfaces, skills, docs, comments | no code bug; stub test wrong under `--enrich`, mislabelled library ceiling error, stale docs |

What made the reviews productive:

- **Measure, don't reason.** Every resource claim was checked with a
  hostile input under a watchdog (RSS limit plus timeout). Several "this is
  bounded" arguments that read correctly were false when measured.
- **Each fix round introduced the next round's top finding.** Round 3's
  bounds were bypassable; round 5a's determinism fix lost model names;
  round 5b's ZIP check was bypassable. A short review of each fix commit
  alone was worth more than another whole-PR pass.
- **Alternate narrow and wide reviews.** Narrow (one fix commit) finds
  regressions in new code; wide with a reviewer that never saw earlier
  rounds (5b) found what anchored reviewers had stopped questioning.
- **Mutation testing as the test-quality check.** Surviving mutants
  pointed at missing boundary tests (exactly-at-cap, budget filled
  exactly), vacuous tests (an assertion that passed with the guarded check
  removed) and equivalent mutants that prove nothing.
- **Agents break process rules under pressure.** Fix agents occasionally
  ran a forbidden git write or wrote outside the scratch area; restating
  the hard rules at the top of every brief, and verifying afterwards,
  was necessary.

## 3. Findings by class

### 3.1 The library parses far more than the SBOM needs

The root cause behind most memory and time findings: a format library
builds its whole in-memory structure to hand back a few header fields.

| Format, library | Hostile input | Measured |
|---|---|---|
| fastText, `load_model` | 308-byte header | 5 GB resident and climbing (full model load) |
| ONNX, `onnx.load` | 16 MiB of empty inputs | 3 GB (protobuf amplification) |
| GGUF, `GGUFReader` | 12 MB: 12 arrays x 1M uint8 | 4.96 GB, 49 s (one numpy view per element) |
| GGUF | 24 MB: arrays nested 5 deep | 3.3 GB |
| GGUF | 39 MB: 1M tensor infos | 3.6 GB, 30 s |
| PyTorch, fickling | pickle | ~200x amplification (one AST node per opcode) |
| Safetensors, `safe_open` | 70 MB `__metadata__` header | 3.8 GB, 12 s |
| Keras/PT2/`.npz`, `zipfile` | `.keras` of 3M empty entries, 16 MiB in the wheel | 1.8 GB (one `ZipInfo` per entry) |

Lessons:

- **Byte ceilings do not bound parser work.** A small file can declare
  millions of elements; the cost is in what the parser builds, not in the
  bytes read. Bounds must be on declared counts and structure, checked
  before the parser runs.
- **A pre-check must agree with the parser exactly.** The GGUF pre-walker
  first skipped scalar arrays ("one numpy view") and treated deep nesting
  as malformed; the library did neither, so each difference was a bypass.
  Rule adopted: anything the library would accept but the pre-check cannot
  follow is refused, not ignored.
- **Count everything into one budget.** Separate caps per kind (tensors,
  pairs, strings) let an attacker spend each to the limit; a single
  weighted budget (tensor/pair weight 4, element 1, from measured cost per
  kind) bounded the total.
- **Version drift is a bypass.** The pre-check knew GGUF v2-v3; a future
  version the library accepts would skip the check. Fail closed on a
  version the library reads but the check does not know.
- **The real fix is not reading the structure at all**: header-only,
  stdlib-only readers that seek past what they do not emit. Planned after
  the 0.20.0 release, tested for parity against the libraries.

### 3.2 Native code in-process

- **libhdf5:** two 8 KiB files, each a 1-27 byte mutation of a valid `.h5`,
  found within a few hundred random mutations: one segfaults the
  interpreter, one busy-loops forever. Committed as regression fixtures.
- **No interrupt.** A Python signal handler does not run while native
  code holds the interpreter, so Ctrl-C and `TerminationGuard` cannot stop
  a hung native parser.
- **Response:** gate the native and amplifying readers (fastText, GGUF,
  HDF5, ONNX, PyTorch pickle) for wheels: list the model with format only,
  plus one `INFO:`, unless the user passes `--trust-wheel-model`. No
  config key for the opt-in, because a config file can live in the
  untrusted tree. Project scans are not gated (the user's own tree), which
  is documented as unsafe for an untrusted checkout.

### 3.3 Archives inside archives

- **Wheel members:** `ZipInfo.file_size` is attacker-controlled. Copy with
  a running byte counter on 8 KiB reads, abort at the ceiling, delete the
  partial file; never `shutil.copyfileobj` without a counter.
  `zf.open()` before creating the target, so an encrypted or unsupported
  member leaves no file.
- **Temp names never derived from member names** (Windows reserved names
  like `CON.npy`, long names, `:` and newlines): `{index}{suffix}` only.
- **Aggregate budget.** A per-member ceiling still lets many members fill
  the disk; a per-wheel budget (4x the ceiling) counts bytes copied and
  bytes read inside model archives.
- **Nested decompression.** A model archive (`.keras`, `.pt`, `.pt2`) is
  itself a zip: a few KiB of deflate inflate to gigabytes. Every inner
  metadata member is read through one helper with `read(CAP + 1)`.
- **Declared lengths inside formats:** numpy reads the declared `.npy`
  header length before checking it; a v2 header declaring 4 GiB in a
  48 MiB deflated member inflated it. Check the length field first.
- **The central directory is a bomb too** (round 5b): `zipfile` builds an
  object per entry before any reader looks. A pre-check of the end record
  was added, then bypassed (round 5c) three ways because it did not find
  the same record `zipfile` uses: `zipfile` looks for the ZIP64 record at
  the locator's offset first; it accepts the last 22 bytes as the end
  record before searching for a signature (a signature planted in the
  record's own fields blinded our search); and CPython 3.10's search
  window is one byte wider than 3.14's. A 268 KB wheel reached 807 MB.
  Also, `zipfile` walks the directory by its byte size and ignores the
  declared entry count, so a lying count passed.
- **Lesson: never re-implement the parser's decision; reuse it.** Fixed
  by calling `zipfile._EndRecData` (the function `ZipFile` itself calls) on
  one handle, pinning its shape with a test, failing closed if it changes,
  and counting the real entries by streaming the directory before
  `ZipFile` runs. A private stdlib name is a lesser risk than a second
  implementation that silently disagrees.
- **"The parser's decision" differs across patch releases of one minor
  version.** The CVE-2025-8291 fix changed what `zipfile._EndRecData`
  reports for a ZIP64 archive (3.11.9 and 3.11.14 disagree), so the start
  of the directory computed for one is 76 bytes off for the other, the walk
  read garbage and "left it to `zipfile`": a bypass. Agree with the running
  interpreter (probe it, do not read the version), fail closed when the walk
  cannot account for the directory, and keep an unpatched interpreter in CI:
  CI's Windows 3.11.9 leg caught it; every local interpreter was patched.
- **Check and use the same handle.** Checking a path and then reopening it
  is a time-of-check/time-of-use gap.

### 3.4 Python runtime surprises

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

### 3.5 Logs and terminals are an output channel

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

### 3.6 Determinism (an SBOM requirement, not a nicety)

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

### 3.7 Transparency: what the SBOM does not say

- **A model that could not be read is still listed**, as a format-only
  entry (the format as its name and a link to the model file, whose hash is
  on the file), with one `WARNING:` or `INFO:` naming why. Dropping it would make the SBOM claim the package
  holds no such model.
- **No silent trims.** An audit found two cuts without a message; one now
  warns, one stays silent by design because nearly every real model would
  trigger it and the value states its own total.
- **Consistency across surfaces.** The CLI on a wheel, the CLI on a single
  model file, the library API and the build hook must record the same
  model the same way. `loom model` kept 1001 entries silently while scans
  warned at 1000; found only by comparing surfaces.
- **A notice must describe what happened.** A gate notice printed on a
  failed scan claimed models "are listed" when no SBOM was written.

### 3.8 Correctness bugs found on the way

- GGUF array fields were emitted as their last element (the last
  vocabulary token's UTF-8 bytes as a property value) since before #263.
  Fixed: an array `k` is now recorded as `k.length`, its declared top-level
  element count (stories260K: `tokenizer.ggml.tokens` 512; phi-3: 32064).
  Element values are never read for the SBOM. The element type in the
  artifact-metadata annotation comes from the array header, not from the
  reader's `types` list, which the library fills from the first element and
  so lacks for an empty array; the library checks an empty array's type
  code nowhere, so an unknown code is left out rather than trusted.
- GGUF quantization was read with the wrong enum: `general.file_type` is a
  `LlamaFileType` (the file's predominant type), but was mapped through the
  per-tensor `GGMLQuantizationType`, which numbers differently. A Q8_0 file
  (`file_type` 7) was reported as `Q5_1`; F16 (1) matched by coincidence,
  which is why the fixtures never showed it. Fixed with the GGUF arrays.
- A detection threshold looser than the refusal cap is required: Safetensors
  is detected by its magic and a header length at most the format's own
  100,000,000 bytes, and refused over Pitloom's 16 MiB. Had detection used
  the 16 MiB cap, a header of 17 MiB would have been "unsupported model
  format" instead of refused with its size. The threshold must also match
  the library's own bound, inclusive or exclusive: the `safetensors`
  library 0.8.0 accepts a declared 100,000,000 and rejects 100,000,001, so
  detection moved from `<` to `<=`.
- A helper reused outside its contract (skip every `*.dist-info/`) let a
  model hide; the narrower rule (the wheel's own dist-info) still let a
  fake `x.dist-info/WHEEL` hide one; final rule: the dist-info named by the
  wheel filename.
- A suffix shared with a non-model file (`.pth` is also Python path
  configuration) needs a content check: accept only a ZIP or a pickle
  protocol 2..5 header.
- `read_wheel` took any `*.dist-info/METADATA`, at any depth, last one
  wins. Real wheels hit it: every setuptools 82-84 wheel was reported as
  `zipp 3.23.0`, a library vendored inside it (8 of the 275 distinct
  wheels of the later survey, which includes the uv cache; flit_core
  escaped only because its vendored folder sorts first).
  Three code paths each had their own "which `.dist-info` is the wheel's
  own" rule; one shared selector now compares the PEP 427 file name with
  the top-level folder the way the ecosystem does (PEP 503 names, PEP 440
  versions; 49 of 126 distinct wheels need that normalisation). The first
  survey, of 126 distinct real wheels, found every one with exactly one matching
  top-level `.dist-info`, so a user option for the fallback was rejected:
  it would cost a flag, config key, Action input and docs for a case
  never seen, and let users switch off the spoofing warning. The 295-wheel
  re-run after the first review round: 283 unchanged, 12 changed
  (setuptools 75.3.2 to 84.0.0, `zipp` to `setuptools`), none refused.
- An unreadable wheel member (corrupt data, invalid UTF-8 name,
  encrypted) crashed the whole run. "Keep the file without a hash" was
  chosen first and then reversed: three consumers (the SBOM builder, the
  registry keyed by path and hash, the package's Merkle root) assume
  every file has a hash, and a package hash that silently skips a file is
  a false integrity claim. The wheel is now refused with one `ERROR:`;
  pip cannot install such a wheel either.
- **Two name lists in one selector** (wheel-identity review): `read_wheel`
  chose the `.dist-info` from normalised member names, the embed from the
  raw `namelist()`. `demo-1.0.dist-info/METADATA` plus
  `demo-1.0.dist-info\METADATA` made one reader report `evil 9`, and the
  embed wrote that into the wheel. Select from one list, built in one place.
- **Duplicate member names are parser confusion**: two readers keeping
  different copies of one name (first, last, or by separator) is how a
  hostile archive shows a scanner one file and an installer another. A
  wheel with one name twice is refused, not resolved by a rule.
- **A byte cap on `METADATA` did not bound memory**: a 28 KB wheel
  inflated to 710 MB resident from 16 MiB of short headers, 2.4 million of
  them once parsed. Parse the header block only (stop at the first blank
  line) and cap the header count (10,000) as well as the bytes.
- **A NUL in a member name is a duplicate in disguise**: `zipfile` cuts
  `ZipInfo.filename` at the NUL (`orig_filename` keeps it), so
  `nul/__init__.py` plus `nul/__init__.py\0.evil` is one file to an
  installer and two to a reader that compares raw names: the SBOM hashed the
  first, pip installed the second, and an embed wrote a wheel with the name
  twice. Any member name holding a NUL refuses the wheel; check the raw
  name, not the one the library hands back.
- **A skip rule must follow the same selector as the identity**: the model
  scan skipped every directory the file name matched, while `read_wheel`
  took none of them as the wheel's own when several matched. A model in
  either of two matching `.dist-info` directories was hidden from the scan
  and the wheel was named `unknown`. Skip only the one directory the
  selector chose; where it chose none, skip nothing.

### 3.9 Found while planning the next fixes (measured)

- **"Is it a model" was inverted** (built, #270). An extension alone made a
  file a model: a 24-byte text file named `.safetensors` became a model entry
  (its text read as an 8-quintillion-byte header length), and Git LFS
  pointer files (text stand-ins for unfetched large files) became 1 entry
  in a project but 5 in a wheel. Meanwhile a genuine but truncated
  Safetensors file was dropped. Decided and built: the file's first bytes must
  not contradict its extension (formats with no reliable signature, ONNX and
  HDF5, go by extension); a contradiction is one `WARNING:`.
- **Whether a model is listed depended on the environment and on order**
  (built, #270). A truncated model was dropped when its library was installed
  and kept when it was not (6 vs 7 entries); under a size budget the same
  wheel gave 8 or 11 entries depending on which files were read first. The
  lesson: **an outcome keyed on the failure kind made the entry set order- and
  environment-dependent.** Every confirmed model is now listed, read or not,
  on every surface, including `loom model FILE`, which stopped with exit 1.
- **A parser can do the dangerous work before the check sees it.**
  `pickletools.genops` converts a decimal number with `int()` before it
  yields the opcode, so a digit cap applied to its output is too late
  (1M digits: 3.4 s, quadratic, when Python's digit limit is off). The
  pickle walk has to be replaced, not wrapped; the default digit limit
  meanwhile turns the same input into a misleading "malformed" warning,
  so the outcome depended on an interpreter setting.

### 3.10 Git LFS pointers (#270, and a policy PR after it)

- **A pointer is exact evidence, not a heuristic.** Git LFS leaves a small
  text file whose first line is `version <spec URL>` until the content is
  fetched; a pointer on disk means "never pulled". git-lfs accepts three
  URLs: `https://git-lfs.github.com/spec/v1` and two legacy aliases,
  `https://hawser.github.com/spec/v1` and `http://git-media.io/v/2`
  (`http`, not `https`). It compares the whole line, so match up to the
  `\n`/`\r\n` terminator (`.../v1x` is not a pointer); git-lfs never
  writes a BOM. The header read grew 9 -> 23 -> 42 -> 44 bytes, driven by
  the longest alias plus its terminator. No false positive: an ONNX
  protobuf cannot start with `v` (wire type 6 is invalid) and the other
  formats open with binary magic.
- **Every suffix class failed differently.** One pointer set gave 1 entry
  in a project and 5 in a wheel; a stub on one command, an `ERROR:` on
  another. Suffixes that trust any header (`.onnx`, `.h5`) became stubs
  with a "corrupt file" warning, a misdiagnosis; `.pt` vanished silently;
  `.bin`/`.zip`, candidates with no named format and the commonest real
  case (`pytorch_model.bin`), were dropped without a word. Each class
  surfaced in a different review round. Lesson: enumerate the suffix
  classes (magic, ZIP, pickle, admit-any, format-less candidates) and test
  one of each, not one suffix.
- **A wrong fixture looked like a code bug.** A reviewer's `.zip` pointer
  used `https://git-media.io/v/2`, which git-lfs rejects, so silence was
  correct. Check a fixture against the format's own spec before filing it.
- **The problem is not limited to models.** Any file can be a pointer: a
  dataset listed as a `software_File` carries the pointer's SHA-256 as its
  `verifiedUsing`, silently; a training run that hashes an unpulled base
  model (`use_model(path=)`) records the pointer as the model's identity
  and splits its lineage when the real file arrives. Decided: one shared
  detector for every place that reads or hashes content; the file stays
  listed with the hash of the bytes really there; one summary `WARNING:`
  per run (the event is "this checkout was not pulled"), one line per file
  at `--debug`; a wheel that ships a pointer is a build bug, same rule.

## 4. Principles that came out of it

1. An SBOM generator must read metadata, never load the artefact the way
   its runtime does.
2. Bound declared structure (counts, lengths, nesting) before any parser
   runs; byte ceilings alone do not bound work.
3. A pre-check must use the parser's own decision procedure, or it will
   disagree with the parser on hostile input. Nuance: a pre-walk built on
   the parser's own decoder inherits its conversions (`genops` calls `int()`
   on decimal text before yielding), so it pays the parser's costs and
   limits before any bound of yours applies. Reuse the opcode table, not
   the decoder.
4. Fail closed on anything the check does not understand (unknown
   versions, a missing private API).
5. Gate native and amplifying parsers for untrusted input; make the
   opt-in explicit and not settable from the untrusted input itself.
6. Keep what cannot be read as a visible, minimal entry with one message;
   never drop it silently.
7. Every cap needs a stable order for what it keeps, a message when it
   bites, and a documented effect on output.
8. Treat logs as an output channel to an untrusted terminal or CI runner.
9. Measure every resource claim with hostile input under a watchdog;
   review every fix commit on its own.
10. A detection threshold must stay looser than the refusal cap, or an
    over-cap file is misclassified rather than refused; and it must match
    the library's own bound, inclusive or exclusive.
11. Take identity from what the artefact declares, chosen by a rule close
    to its ecosystem's installer (Pitloom is laxer: where the file name names
    none it falls back to a single mismatched `.dist-info` with a `WARNING:`,
    where pip refuses), and check the rule against real artefacts before
    adding options for cases nobody has.
12. Decide "is this a model" from content that cannot contradict the
    name, and once decided, list it whatever happens when reading it. A
    suffix that trusts any header (`.onnx`, `.h5`) is still contradicted by
    a known text signature: a Git LFS pointer is no model under any suffix.
13. Never decode a numpy `object` array through `tobytes()`: it holds
    pointers, so the "text" differs per run. Decode per element, but only
    where `dtype.hasobject`: a fixed-length `S`/`U` array has stable bytes
    and must keep a bulk path (a Python object per element costs ~160
    bytes; a fix for one bug class, pointer bytes, must not open another,
    memory). Decide on `dtype.hasobject`, not `kind`: a compound dtype with
    a string field has `kind == "V"` and still holds pointers.
14. A value read from untrusted JSON that reaches a typed output field
    (a name, a class) needs a type check, and deep nesting needs a
    `RecursionError` guard; both are per-attribute problems, not a crash.
15. A value can have a dtype and no data: an HDF5 attribute with an empty
    dataspace (`h5py.Empty`) has `.dtype` but no `reshape`/`tolist`, so a
    decoder that dispatches on `dtype` alone raises `AttributeError`, outside
    the errors an attribute read catches. Treat it as absent.
16. A placeholder for content that was never fetched (a Git LFS pointer)
    is a state of the checkout, not of one file: detect it exactly, report
    it once per run, and never let its bytes stand for the content's
    identity (a model entry, a registry key).

## 5. Status at the time of writing

- #263 after round 7: the ZIP check (round 5c) uses `zipfile._EndRecData` on
  one handle and walks the real directory; every round-5c repro is refused at
  43-65 MB (was 797-844 MB), on 3.10 and 3.14, and the hostile wheel scan
  dropped from 831 MB to 44 MB.
- Header-only readers planned after the 0.20.0 release: they remove the
  library-amplification and native-code classes (3.1, 3.2, most of 3.4's
  stderr work) but not the archive, determinism and transparency classes;
  see [model-metadata-readers.md](../design/model-metadata-readers.md),
  "What the readers remove, and what stays".
