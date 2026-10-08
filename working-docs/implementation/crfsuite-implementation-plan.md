---
Created: 2026-10-08
Last-Modified: 2026-10-08
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# CRFsuite support: implementation plan

Record of the step plan (agents of different capability) the support was
built from, trimmed to what the code and tests do not say: order, the
reader's check order, judgement calls and traps. Read
[crfsuite-support.md](crfsuite-support.md) (decisions and format) first. Every format fact was checked against
CRFsuite's source (`chokkan/crfsuite` at `dc5b6c7`, the commit
python-crfsuite 0.9.12 vendors) and real files; anything not verified says
so.

Status: built in PR #294.

See also: [crfsuite-support.md](crfsuite-support.md),
[model-metadata-readers.md](../design/model-metadata-readers.md) (the
`formats/` subpackage rules), CLAUDE.md (binding for every step).

## Ground rules and tiers

- The user does all git writes; one step per agent session; tier-1 checks
  at the end of a step, saying what was not run.
- Each new test must fail on the tree before the step (prove it on a
  scratch copy, never by editing the shared tree back).
- Model tiers: **S** small model, mechanical and fully specified; **M**
  mid model; **L** strongest model, for hostile input and review.

| Step | What | Tier |
|---|---|---|
| 0 | fastText `labels` as a JSON array (see below) | S |
| 1 | Fixtures and generator | S |
| 2 | `formats/crfsuite.py` reader | L |
| 3 | Adversarial tests and fuzz target | L |
| 4 | Adapter `extract/ai_model/crfsuite.py` and registry | M |
| 5 | One source for model suffixes | M |
| 6 | Surface tests | M |
| 7 | Docs, skills, plugin, CHANGELOG | S |
| 8 | Review loop, mutation testing, real files | L |

Format facts and the twelve traps are in
[crfsuite-support.md](crfsuite-support.md#traps).

## Step 0: label lists are JSON arrays

Every reader that records a label list in `properties` writes a JSON array
string, never a comma-joined one (a label may contain `,`). fastText was
comma-joined; it now writes `canonical_json(labels)` (RFC 8785, label
order as read, never sorted), and CRFsuite does the same. Trap: the
metadata-only fastText reader planned in
[model-metadata-readers.md](../design/model-metadata-readers.md) must
produce the same array; its parity test compares against this reader.
Regression cases: a label containing `,` and one containing `"`
round-trip through `json.loads`.

## Step 1: fixtures

`tests/fixtures/aimodels/crfsuite/generate_fixtures.py` trains two tiny
models with python-crfsuite 0.9.12 in a throwaway venv (never a Pitloom
dependency); tests never import or run it. Outputs: `complete.crfsuite`
(5 labels incl. Thai, a space, punctuation; 14 attributes; 24 features)
and `minimal.model` (labels `I`, `E`; 2 attributes; 4 features). Sizes and
sha256 are in `tests/fixtures/aimodels/details/crfsuite.md`; the reader
tests pin the counts. Fixture globs go in the sdist `exclude` list in
`pyproject.toml` with the other formats'. Hostile variants are derived in
memory in step 3, never committed.

## Step 2: the reader

Rules ([model-metadata-readers.md](../design/model-metadata-readers.md)):
stdlib only, relative imports only, no logging, no global state, errors
from `formats._errors`. Two new `Limits` fields
(`max_crfsuite_labels`, `max_crfsuite_labels_chunk_bytes` = 1 MiB; a field left
out of the hard-coded tuple in `__post_init__` is not validated). Total
read is bounded by the labels chunk plus the chunk headers, never by the
attribute or feature counts.

Checks, in this order (never read before the check that bounds the read):

| # | Check | Error |
|---|---|---|
| 1 | file size >= 48 | `Malformed("header truncated")` |
| 2 | magic `lCRF` | `Malformed` |
| 3 | type `FOMC`, version 100 | `UnsupportedVersion` |
| 4 | `48 <= header.size <= file size` (bytes past `size` are ignored; `size` past the end means truncation) | `Malformed` |
| 5 | `48 <= off_features < off_labels < off_attrs < off_labelrefs < off_attrrefs`, and each offset plus its chunk header fits in `size` | `Malformed` |
| 6 | FEAT tag; `FEAT.size == 12 + 20 * num`; ends at or before `off_labels` | `Malformed` |
| 7 | `num_labels <= limits.max_crfsuite_labels` | `LimitExceeded` |
| 8 | labels CQDB: tag, `byteorder == 0x62445371`, `flag == 0` | `Malformed` / `UnsupportedVersion` for byte order and flag |
| 9 | `2072 <= cqdb.size <= off_attrs - off_labels` (the writer pads even an empty CQDB to its first record) and `cqdb.size <= limits.max_crfsuite_labels_chunk_bytes` | `Malformed` / `LimitExceeded` |
| 10 | `bwd_size == num_labels`; if non-zero, `2072 <= bwd_offset` and `bwd_offset + 4 * n <= cqdb.size`. Then the 256 hash-table refs: `sum(num // 2) == bwd_size` and every non-empty table `2072 <= offset`, `offset + 8 * num <= cqdb.size` (CRFsuite sizes its backward array from the refs and reads past its buffers, or crashes, when they lie) | `Malformed` |
| 11 | per id: `2072 <= rec_off <= cqdb.size - 8`; record id equals its index; `1 <= ksize`; key ends inside the chunk; last key byte is NUL | `Malformed` |
| 12 | attributes CQDB header: tag, byte order, `2072 <= size <= off_labelrefs - off_attrs`, `bwd_size == num_attrs`, the backward array inside the chunk (as 10), and `off_attrrefs + 12 + 4 * num_attrs <= header.size`. Only the labels CQDB's hash-table refs are checked; the attributes chunk's are not, as its strings are never read | `Malformed` |
| 13 | LFRF and AFRF tags; `AFRF.num == num_attrs`; `LFRF` offset array fits before `AFRF` (`LFRF.num` is `num_labels + 2` in every file seen, so it is bounded, not compared) | `Malformed` |

Judgement calls:

- Check 10 exists because CRFsuite itself sizes its backward array from
  the refs and reads past its buffers, or crashes, when they lie.
- Only the labels CQDB's hash-table refs are checked; the attributes
  chunk's are not, as its strings are never read.
- A short read is truncation even when `size` lied (`_read_exact`).
- Labels decode with `backslashreplace`, and an inner NUL ends the label.

## Step 3: adversarial tests

One `parametrize` entry per check above, built from `complete.crfsuite`
in memory, asserting the error class and a short stable substring of the
reason. Boundaries worth keeping: truncation at 0, 47, 48, half, size-1;
`size` 0, 47, file size + 1; trailing garbage (must read the same: assert
the bytes changed); `num_labels` = 100 (CRFsuite segfaults on it);
invalid UTF-8 and inner-NUL labels; zero labels. A property test truncates
and flips every byte of `minimal.model` and requires a `CrfsuiteModel` or
a `FormatError`, never another exception. The atheris target is
`fuzz/fuzz_crfsuite_header.py` (listed in the fuzz workflow and
[fuzzing.md](fuzzing.md)).

## Step 4: adapter and registry

`CRFSUITE = ("crfsuite", (".crfsuite",), b"lCRF")` in
`core/ai_metadata.py`; the adapter follows `safetensors.py` and maps
`LimitExceeded` to `ModelLimitExceeded`, other `FormatError` and `OSError`
to `ValueError`. Registered in `extract/ai_model/reader.py` with no
`reader_requirements` entry and not in `WHEEL_GATED_FORMATS` (pure Python,
bounded). The field mapping is in the adapter and
[crfsuite-support.md](crfsuite-support.md#decisions-2026-10-08).

- Property provenance is written by hand, not with
  `record_dict_field_provenance()`: that helper would cite
  `Field: num_features`, the header field that is always 0
  ([trap 1](crfsuite-support.md#traps)).
- The description names at most 20 labels, each cut to 64 characters (a
  label can be 1 MiB), then `... (N more)`.
- `outputs` follows fastText: one entry with the class count, never the
  label strings.
- SPDX 3.1 `additionalInformation`
  ([spdx-3-model#1267](https://github.com/spdx/spdx-3-model/pull/1267))
  may later hold labels and counts natively; no change until released.

## Step 5: one source for model suffixes

Two lists decided "could be a model" (the scanner's `_ALLOWED_EXTS` and
`loom generate FILE`'s `_MODEL_FILE_EXTENSIONS`); adding `.model` by hand
to both would repeat the drift CLAUDE.md warns about. Both now derive from
`core.ai_metadata.model_file_suffixes()` (`SHARED_MODEL_SUFFIXES`
`.bin`/`.model` plus every format extension); `.zip` stays scanner-only. A
drift-guard test pins both consumers. `loom id generate` reaches `.model`
through the scanner's list. Behaviour tests: a SentencePiece-shaped
`.model` logs nothing at `INFO` or above and lists no model; `loom model`
refuses it; a Git LFS pointer named `x.model` warns once
([trap 10](crfsuite-support.md#traps)).

## Step 6: surface tests

Project scan, wheel scan and `loom model` give the same entry and the same
single `WARNING:` for a truncated copy (CRFsuite is read inside wheels
without `--trust-wheel-model`); two `loom project` runs are byte-identical.
Manual check 17 (`scripts/manual_cli_checks/_checks_model.py`) gained a
LFS pointer named `x.model` and a truncated CRFsuite file. No new CLI
option, so `_matrix_plan.py` needed nothing.

## Step 7: docs

Grep every place listing formats (`grep -rn "fastText" docs README.md
skills .claude-plugin`) rather than trusting a list. The `method` rows
`crfsuite_model_type` and `generated_from_labels` go in
`docs/metadata-provenance.md`; `tests/test_provenance_method_rows.py`
now fails on a missing row.

## Step 8: review loop

Repeat until a round finds nothing above cleanup. Mutants worth keeping:
each check in the step 2 table removed or off by one, `ksize` without the
`- 1`, chunk-relative offset made file-relative, label order sorted,
`header.num_features` instead of `FEAT.num`. Real files (manual, not
committed): `loom project /Users/arthit/projects/pythainlp` lists five
CRFsuite `ai_AIPackage`s with the label counts in
[crfsuite-support.md](crfsuite-support.md), no `WARNING:`.
