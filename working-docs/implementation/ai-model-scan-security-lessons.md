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
  4 min extrapolated at an 8 MiB pickle. Do not let a decoder convert
  numbers you do not need.
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
  of a hostile pickle within an opcode cap.

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
  Still open: the fix is planned before 0.20.0.
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
  never seen, and let users switch off the spoofing warning. Re-run after
  the first review round on 295 unique wheels: 283 unchanged, 12 changed
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

### 3.9 Found while planning the next fixes (measured, not yet built)

- **"Is it a model" was inverted.** An extension alone made a file a
  model: a 24-byte text file named `.safetensors` became a model entry
  (its text read as an 8-quintillion-byte header length), and Git LFS
  pointer files (text stand-ins for unfetched large files) became 1 entry
  in a project but 5 in a wheel. Meanwhile a genuine but truncated
  Safetensors file was dropped. Decided: the file's first bytes must not
  contradict its extension (formats with no reliable signature, ONNX and
  HDF5, go by extension); a contradiction is one `WARNING:`.
- **Whether a model is listed depended on the environment and on order.**
  A truncated model was dropped when its library was installed and kept
  when it was not (6 vs 7 entries); under a size budget the same wheel
  gave 8 or 11 entries depending on which files were read first. Decided:
  every confirmed model is listed, read or not, on every surface,
  including `loom model FILE`, which used to stop with exit 1.
- **A parser can do the dangerous work before the check sees it.**
  `pickletools.genops` converts a decimal number with `int()` before it
  yields the opcode, so a digit cap applied to its output is too late
  (1M digits: 3.4 s, quadratic, when Python's digit limit is off). The
  pickle walk has to be replaced, not wrapped; the default digit limit
  meanwhile turns the same input into a misleading "malformed" warning,
  so the outcome depended on an interpreter setting.
- **GGUF arrays reported their last element**, in three places
  (properties, the metadata annotation, hyperparameters); an empty array
  showed `'0'` and a nested one its last leaf. Decided: an array is
  recorded only by its length and element type. Each output place uses
  the most parseable shape it allows: SPDX `DictionaryEntry` properties
  cannot nest, so `<key>.length`; the JSON metadata annotation keeps the
  file's own key with `{"length": N, "type": ...}`, so a derived length
  can never be mistaken for a real dotted GGUF key; provenance names the
  real key plus `Method: array_length`, never a key the file lacks.

## 4. Principles that came out of it

1. An SBOM generator must read metadata, never load the artefact the way
   its runtime does.
2. Bound declared structure (counts, lengths, nesting) before any parser
   runs; byte ceilings alone do not bound work.
3. A pre-check must use the parser's own decision procedure, or it will
   disagree with the parser on hostile input.
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
10. Take identity from what the artefact declares, chosen by a rule close
    to its ecosystem's installer (Pitloom is laxer: where the file name names
    none it falls back to a single mismatched `.dist-info` with a `WARNING:`,
    where pip refuses), and check the rule against real artefacts before
    adding options for cases nobody has.
11. Decide "is this a model" from content that cannot contradict the
    name, and once decided, list it whatever happens when reading it.

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
