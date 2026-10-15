---
Created: 2026-10-15
Last-Modified: 2026-10-15
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# AI model scan lessons: transparency and correctness

See also: [ai-model-scan-security-lessons.md](ai-model-scan-security-lessons.md)
(the entry page: setting, how the problems were found, principles),
[ai-model-scan-security-lessons-parsers-and-archives.md](ai-model-scan-security-lessons-parsers-and-archives.md)
(sections 3.1-3.3),
[ai-model-scan-security-lessons-runtime-and-output.md](ai-model-scan-security-lessons-runtime-and-output.md)
(sections 3.4-3.6).

## 3.7 Transparency: what the SBOM does not say

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

## 3.8 Correctness bugs found on the way

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

## 3.9 Found while planning the next fixes (measured)

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

## 3.10 Git LFS pointers (#270, and a policy PR after it)

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
