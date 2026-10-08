---
Created: 2026-10-08
Last-Modified: 2026-10-08
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# CRFsuite support: implementation plan

Step-by-step plan for agents of different capability. Read
[crfsuite-support.md](crfsuite-support.md) (decisions and format) first;
this file is the how. Every format fact here was checked against CRFsuite's
source (`chokkan/crfsuite` at `dc5b6c7`, the commit python-crfsuite 0.9.12
vendors) and real files; anything not verified says so.

See also: [model-metadata-readers.md](model-metadata-readers.md) (the
`formats/` subpackage rules), AGENTS.md (binding for every step).

## Ground rules for every step

- Branch from current `main`; the user does all git writes. Never commit,
  stash or check out; leave changes in the working tree.
- One step per agent session; finish with tier-1 checks (touched tests,
  `ruff format`, `ruff check`, `mypy`), and say what was not run.
- Each new test must fail on the tree before the step (prove it on a
  scratch copy, never by editing the shared tree back).
- Model tiers: **S** small/cheap model, low effort (mechanical, fully
  specified); **M** mid model, medium effort; **L** strongest model, high
  effort (hostile input, open judgement, review).

| Step | What | Tier | Depends on |
|---|---|---|---|
| 0 | fastText `properties["labels"]` as a JSON array (own small PR, first) | S | -- |
| 1 | Fixtures and generator | S | -- |
| 2 | `formats/crfsuite.py` reader | L | 1 |
| 3 | Adversarial tests for the reader | L | 2 |
| 4 | Adapter `extract/ai_model/crfsuite.py` + registry | M | 2 |
| 5 | Shared model-suffix constant, `.model` candidates | M | 4 |
| 6 | Surface tests (scan, wheel, `loom model`, parity) | M | 4, 5 |
| 7 | Docs, skills, plugin, CHANGELOG | S | 4-6 |
| 8 | Review loop, mutation, manual checks, real files | L | all |

## Format facts the code depends on

All integers are little-endian `uint32`, written byte by byte
(`crf1d_model.c` `write_uint32`, not host order).

Header, 48 bytes, struct `<4sI4sIIIIIIIII`: `magic` `lCRF`, `size`,
`type` `FOMC`, `version` 100, `num_features`, `num_labels`, `num_attrs`,
`off_features`, `off_labels`, `off_attrs`, `off_labelrefs`,
`off_attrrefs`. Chunks follow in exactly that order: `FEAT`, labels
`CQDB`, attributes `CQDB`, `LFRF`, `AFRF`; on every file seen, each chunk
ends where the next starts and `AFRF` ends at `size`.

- `FEAT`: `<4sII` tag, size, num; then `num` records of 20 bytes, so
  `size == 12 + 20 * num`.
- `CQDB`: 24-byte header `<4sIIIII` = tag, `size` (whole chunk, header
  included), `flag`, `byteorder` (`0x62445371`), `bwd_size`, `bwd_offset`;
  then 256 table refs `{offset, num}` (2048 bytes); records start at
  `OFFSET_DATA = 2072`. A record is `<iI` id, `ksize` (string length **plus
  the NUL**), then the key bytes and the NUL. Then the hash tables, then the
  backward array: `bwd_size` uint32 record offsets indexed by id. **All
  CQDB offsets are relative to the CQDB chunk start**, not the file.
- `LFRF`/`AFRF`: `<4sII` tag, size, num; then offsets and per-item lists.
  `AFRF.num == num_attrs`; `LFRF.num` is `num_labels + 2` on every file
  seen, reason not found in the source: do not check it.

### Traps (read before writing code)

1. **`header.num_features` is always 0.** The writer never sets it. The
   real count is `FEAT.num`.
2. **CRFsuite validates almost nothing.** Its loader checks only that the
   file is over 48 bytes; python-crfsuite adds a magic check. It ignores
   `size`, `type`, `version` and trailing bytes, and **segfaults** on a bad
   label offset, a wrong byte-order mark or an inflated `num_labels`
   (measured). "As lenient as CRFsuite" is not a goal; every bound below is
   ours.
3. **Record offsets are chunk-relative; `ksize` counts the NUL.** Off by
   the chunk offset or by one byte reads garbage that still looks like a
   string.
4. **Label order is meaningful.** Ids are assigned in first-seen training
   order; the backward array is indexed by id. Keep that order; never sort
   labels (determinism comes from the file, not from sorting).
5. **Labels are bytes.** CRFsuite does no encoding; python-crfsuite writes
   UTF-8 but accepts `bytes` labels, and then cannot load the model it
   wrote (`UnicodeDecodeError`). Decode with
   `errors="backslashreplace"`: never crash, never guess an encoding.
6. **An embedded NUL truncates** in CRFsuite (C strings). Take the bytes
   before the first NUL, as CRFsuite does.
7. **Zero labels and zero attributes are valid on disk** (an empty training
   set saves). `bwd_offset` is 0 when a CQDB has no records.
8. **`flag` is always 0.** `CQDB_ONEWAY` (`0x1`) would drop the backward
   array, making labels unreadable by id; the CRF writer never sets it.
9. **Never read attribute strings.** Thousands per model, training-text
   features (privacy). Read only the attributes CQDB header (24 bytes).
10. **`.model` is a shared suffix** (SentencePiece, gensim and others). A
    `.model` without `lCRF` must stay silent, exactly as a non-model `.bin`
    is today; a `.crfsuite` without `lCRF` warns (a contradicted suffix,
    like `.gguf`). Do not put `.crfsuite` in `_EXTENSION_ADMITS`.
11. **A labels list inside `raw_metadata` is one entry** to
    `cap_entries()`; the generic cap never shortens it. The reader caps the
    label count itself.
12. **Fixture bytes are not proven identical across platforms** (float
    weights; identical across runs and processes on one macOS arm64
    machine only). Commit the binaries; tests never regenerate them.

## Step 0: fastText labels as a JSON array (S, own PR)

Decided 2026-10-08: every reader that records a label list in
`properties` writes a JSON array string, never a comma-joined one (a label
may contain `,`). fastText comma-joins today
(`extract/ai_model/fasttext.py`, `properties["labels"] =
",".join(labels)`); CRFsuite must not copy that.

- Change it to `json.dumps(list(labels), ensure_ascii=False)`; keep the
  label order as read (never sort). `outputs` and its provenance stay.
- Update the tests that split or substring-match the string
  (`tests/extract/ai_model/test_fasttext_mocked.py`,
  `test_fasttext_integration.py`: parse with `json.loads`, then compare
  lists) and `tests/fixtures/aimodels/details/fasttext.md` (two lines
  describe the comma-separated value).
- Add an adversarial case: a label containing `,` and one containing `"`
  round-trip through `json.loads` unchanged.
- Grep docs and skills for the old shape (`comma-separated`, `labels`);
  CHANGELOG `### Changed`: one bullet (SBOM output changes).
- Trap: the metadata-only fastText reader planned in
  [model-metadata-readers.md](model-metadata-readers.md) must produce the
  same JSON array; its parity test compares against this reader.

## Step 1: fixtures and generator (S)

Files:

- `tests/fixtures/aimodels/crfsuite/generate_fixtures.py`: the generator.
  Not imported by tests. Header comment says how to run it and that the
  committed binaries are the reference.
- `tests/fixtures/aimodels/crfsuite/complete.crfsuite` and
  `tests/fixtures/aimodels/crfsuite/minimal.model`: its output.
- `tests/fixtures/aimodels/details/crfsuite.md`, rows in
  `tests/fixtures/aimodels/README.md` (subdirectory list, table with
  source and licence CC0-1.0, details link), and the sdist globs in
  `pyproject.toml` next to the other formats' fixture globs.

Generator (python-crfsuite 0.9.12 in a throwaway venv; it is never a
Pitloom dependency or dependency-group member):

```python
"""Generate the CRFsuite test fixtures (python-crfsuite 0.9.12).

python -m venv /tmp/crf && /tmp/crf/bin/pip install python-crfsuite==0.9.12
/tmp/crf/bin/python generate_fixtures.py
"""
from pathlib import Path

import pycrfsuite

HERE = Path(__file__).parent

# Labels: Thai, a space, punctuation; first-seen order = id order
COMPLETE_X = [
    [["w=บุคคล", "pos=NN", "bias"], ["w=ไป", "pos=VB", "bias"],
     ["w=กรุงเทพ", "pos=NNP", "bias"]],
    [["w=อ", "pos=NN", "bias"], ["w=x y", "pos=VB"],
     ["w=Paris", "pos=NNP", "bias"]],
    [["w=ก", "pos=NN"], ["w=ข", "pos=NN"], ["w=ค", "pos=VB"],
     ["w=ง", "pos=NNP"]],
]
COMPLETE_Y = [
    ["บุคคล", "O", "B-LOC"],
    ["I PER/x", "O", "B-LOC"],
    ["บุคคล", "I PER/x", "O", "E-X:1"],
]
MINIMAL_X = [[["a"], ["b"]], [["b"], ["a"]]]
MINIMAL_Y = [["I", "E"], ["E", "I"]]


def train(xs, ys, path: Path) -> None:
    trainer = pycrfsuite.Trainer(algorithm="lbfgs", verbose=False)
    for x, y in zip(xs, ys):
        trainer.append(x, y)
    trainer.set_params({"max_iterations": 20})
    trainer.train(str(path))


train(COMPLETE_X, COMPLETE_Y, HERE / "complete.crfsuite")
train(MINIMAL_X, MINIMAL_Y, HERE / "minimal.model")
```

Expected (measured): `complete.crfsuite` 5,656 bytes, labels
`บุคคล, O, B-LOC, I PER/x, E-X:1`, 14 attributes, 24 features;
`minimal.model` 4,484 bytes, labels `I, E`, 2 attributes, 4 features.
Record both sha256 values in `details/crfsuite.md`. If the sizes differ,
stop and report: the reader tests in step 2 pin these numbers.

Hostile variants are **not** committed; step 3 derives them from these
two files in memory.

## Step 2: the reader, `formats/crfsuite.py` (L)

Rules from `model-metadata-readers.md` and the existing
`formats/pickle_walk.py`: stdlib only, relative imports only (the
isolation test scans every module in `formats/` automatically), no
logging, no global state, errors from `formats._errors`, typed, docstring
with "See also" to the adapter.

`formats/_limits.py`: add two fields and extend the hard-coded tuple in
`__post_init__` (it validates fields by name; a field left out is not
validated):

```python
max_crfsuite_labels: int = 1000
max_crfsuite_label_bytes: int = 1 << 20  # labels CQDB chunk, read whole
```

`formats/__init__.py`: list the module in the docstring's "Modules:".

API (a `NamedTuple`, like `pickle_walk`'s results):

```python
class CrfsuiteModel(NamedTuple):
    """What a CRFsuite model file says about itself."""

    model_type: str  # "FOMC"
    version: int  # 100
    num_features: int  # FEAT.num, never header.num_features
    num_attributes: int
    labels: tuple[str, ...]  # id order


def read_crfsuite(
    source: IO[bytes], limits: Limits = Limits()
) -> CrfsuiteModel:
    """Read a CRFsuite model's header and label strings, nothing else.

    *source* is a seekable binary file. Reads the 48-byte header, the
    FEAT/LFRF/AFRF chunk headers, the labels chunk (whole, bounded) and
    the attributes chunk header: at most
    ``limits.max_crfsuite_label_bytes + 108`` bytes.
    """
```

Checks, in this order (each a distinct `reason`; never read before the
check that bounds the read):

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
| 9 | `24 <= cqdb.size <= off_attrs - off_labels` and `cqdb.size <= limits.max_crfsuite_label_bytes` | `Malformed` / `LimitExceeded` |
| 10 | `bwd_size == num_labels`; if non-zero, `2072 <= bwd_offset` and `bwd_offset + 4 * n <= cqdb.size` | `Malformed` |
| 11 | per id: `2072 <= rec_off <= cqdb.size - 8`; record id equals its index; `1 <= ksize`; key ends inside the chunk; last key byte is NUL | `Malformed` |
| 12 | attributes CQDB header: tag, byte order, `bwd_size == num_attrs`, chunk ends at or before `off_labelrefs` | `Malformed` |
| 13 | LFRF and AFRF tags; `AFRF.num == num_attrs` | `Malformed` |

Core of check 11 (the part most likely to be written wrong):

```python
chunk = _read_exact(source, off_labels, cqdb_size)  # one bounded read
labels = []
for label_id in range(num_labels):
    (rec_off,) = struct.unpack_from("<I", chunk, bwd_offset + 4 * label_id)
    if not _DATA_START <= rec_off <= cqdb_size - 8:
        raise Malformed(f"label {label_id} record outside its chunk")
    rec_id, ksize = struct.unpack_from("<iI", chunk, rec_off)
    key_end = rec_off + 8 + ksize
    if rec_id != label_id or ksize < 1 or key_end > cqdb_size:
        raise Malformed(f"label {label_id} record is inconsistent")
    if chunk[key_end - 1] != 0:
        raise Malformed(f"label {label_id} is not NUL-terminated")
    key = chunk[rec_off + 8 : key_end - 1].split(b"\0", 1)[0]
    labels.append(key.decode("utf-8", errors="backslashreplace"))
```

`_read_exact(source, offset, n)` seeks and reads exactly `n` bytes or
raises `Malformed` (a short read is truncation even when `size` lied).

Unit tests (`tests/extract/ai_model/formats/test_crfsuite.py`), on the two
fixtures: every field equals the numbers in step 1; labels in id order;
reading the PyThaiNLP files is a manual check, not a test (no licence).

## Step 3: adversarial tests (L)

`tests/extract/ai_model/formats/test_crfsuite_hostile.py`. Build each case
from `complete.crfsuite` bytes in memory with a small patch helper, one
`parametrize` entry per check in the table above, short `ids=`:

```python
def _patched(data: bytes, offset: int, fmt: str, *values: int) -> bytes:
    out = bytearray(data)
    struct.pack_into(fmt, out, offset, *values)
    return bytes(out)
```

Cases (each asserts the exact error class and a stable substring of
`reason`, never the whole message):

- truncation at 0, 47, 48, half the file, size - 1;
- `size` 0, 47, file size + 1; trailing garbage appended (must read
  fine and give the same result as the original: assert the bytes did
  change);
- type `ABCD`, version 99 and 101;
- each offset: 0, inside the header, past the end, swapped with its
  neighbour;
- FEAT: wrong tag, `size` not `12 + 20 * num`;
- `num_labels` = 100 (CRFsuite segfaults on this), `limits.max + 1`;
- labels CQDB: wrong tag, byte order swapped, `flag = 1`, `size` 23, size
  over the limit (use a small `Limits` instead of a big file);
- backward array offset past the chunk, record offset below 2072, record id
  mismatch, `ksize` 0, `ksize` past the chunk, missing NUL;
- a label with invalid UTF-8 (`b"\xff\xfe"`) reads as `\\xff\\xfe`, no
  error; a label with an inner NUL reads up to the NUL;
- zero labels (patch a minimal model or build one): `labels == ()`.

Plus a property test: for every byte position of `minimal.model`,
truncating there and flipping that byte each give either a
`CrfsuiteModel` or a `FormatError`, never another exception (4,484
positions, fast). Add an atheris target to the `fuzz` group next to the
existing ones.

## Step 4: adapter and registry (M)

`src/pitloom/core/ai_metadata.py`:

```python
CRFSUITE = ("crfsuite", (".crfsuite",), b"lCRF")
```

`src/pitloom/extract/ai_model/crfsuite.py`, modelled on `safetensors.py`
(the closest header-only reader) and `_pickle_bounds.py` (error mapping):

```python
_DESCRIPTION_LABELS = 20  # labels named in the generated description


def read_crfsuite_model(model_path: Path) -> AiModelMetadata:
    try:
        with model_path.open("rb") as handle:
            model = read_crfsuite(handle, _LIMITS)
    except LimitExceeded as exc:
        raise ModelLimitExceeded(exc.reason) from None
    except FormatError as exc:
        raise ValueError(f"not a readable CRFsuite model: {exc.reason}") from exc
    source = f"Source: {sanitize_provenance_text(model_path.name)}"
    ...
```

`_LIMITS = Limits(max_crfsuite_labels=MAX_MODEL_ENTRIES)`. An `OSError`
propagates as in the other readers (check what `safetensors.py` does and
match it).

Field mapping:

| `AiModelMetadata` | Value | Provenance |
|---|---|---|
| `name`, `version`, `license` | `None` (not in the file; `resolve_name()` gives the stem) | none |
| `type_of_model` | `"conditional random field"` | `{source} \| Field: type \| Method: crfsuite_model_type` (`FOMC` is the CRF type) |
| `format_info.framework` | `"crfsuite"` | `{source} \| Field: magic` |
| `format_info.format_version` | `"100"` | `{source} \| Field: version` |
| `description` | generated (below), only when labels exist | `{source} \| Field: labels \| Method: generated_from_labels` |
| `outputs` | `[{"name": "label_sequence", "shape": [n]}]` when labels exist | `{source} \| Field: labels (label count)` |
| `properties` | `labels` (JSON array string), `num_labels`, `num_attributes`, `num_features`, `model_type` | `record_dict_field_provenance(...)` |
| `raw_metadata` | same keys, native types (`labels` a list) | -- |

```python
def _description(labels: tuple[str, ...]) -> str | None:
    if not labels:
        return None
    shown = ", ".join(labels[:_DESCRIPTION_LABELS])
    more = len(labels) - _DESCRIPTION_LABELS
    suffix = f", ... ({more} more)" if more > 0 else ""
    noun = "label" if len(labels) == 1 else "labels"
    return f"CRFsuite model with {len(labels)} {noun}: {shown}{suffix}"
```

`properties["labels"] = json.dumps(list(labels), ensure_ascii=False)`: a
JSON array, as fastText after step 0.

`outputs` follows fastText: one entry naming the output and its class
count, never the label strings (they are already in properties and the
description):

```python
outputs = [{"name": "label_sequence", "shape": [len(labels)]}] if labels else []
# provenance["outputs"] = f"{source} | Field: labels (label count)"
```

A CRF emits one label per input item, chosen from `len(labels)` classes.
`outputs` is Pitloom's internal record; today it reaches the SBOM inside
`ai_informationAboutApplication` (JSON). SPDX 3.1's `additionalInformation`
dictionary ([spdx-3-model#1267](https://github.com/spdx/spdx-3-model/pull/1267),
open) may later hold labels and counts natively; no change until it is
released.

Registry: add a `FormatInfo` to `REGISTRY` in
`extract/ai_model/reader.py` (alphabetical), the module docstring lists
in `reader.py` and `extract/ai_model/__init__.py`. No
`reader_requirements` entry (stdlib only); not in `WHEEL_GATED_FORMATS`
(a pure-Python bounded reader is not gated).

Tests (`tests/extract/ai_model/test_crfsuite.py`): both fixtures through
`read_ai_model()`; description cut at 20 (build a 25-label case with a
patched minimal model or via the reader's dataclass, not a new fixture);
`properties["labels"]` round-trips through `json.loads`; provenance keys;
an error from step 3's cases becomes `ValueError` or `ModelLimitExceeded`.
Add the fixture rows to `test_ai_model_header.py`'s detection table
(`complete.crfsuite` and `minimal.model` give `CRFSUITE`; a `.crfsuite`
of text and a `.model` of text give `UNKNOWN`).

**Check, do not assume:** a fragment or registry description must win over
the generated one. Find how a scanned model's `description` merges with a
fragment's (`pitloom.core` fragment merge, `sbom-enrich`); if the
generated text can block a real one, stop and report: the fix is a merge
rule, not a reader change.

## Step 5: one source for model suffixes (M)

Today two hand-kept lists decide "could be a model": the scanner's
`_ALLOWED_EXTS` (`extract/scanner.py`, enum extensions plus `.zip`,
`.bin`) and `loom generate FILE`'s `_MODEL_FILE_EXTENSIONS`
(`assemble/__init__.py`, a literal tuple without `.zip`). Adding `.model`
by hand to both repeats the drift AGENTS.md warns about.

- Add to `core/ai_metadata.py` (next to the enum):

  ```python
  # Suffixes several formats share; a file with one is a model only when its
  # header proves a format.
  SHARED_MODEL_SUFFIXES: frozenset[str] = frozenset({".bin", ".model"})


  def model_file_suffixes() -> frozenset[str]:
      """Every suffix a model file of a supported format can have."""
      return SHARED_MODEL_SUFFIXES | {
          ext for fmt in AiModelFormat for ext in fmt.extensions
      }
  ```

- Scanner: `_ALLOWED_EXTS = model_file_suffixes() | {".zip"}` (`.zip`
  stays scanner-only: a zip is an sdist to `loom generate`).
- `assemble/__init__.py`: `_MODEL_FILE_EXTENSIONS =
  tuple(sorted(model_file_suffixes()))`. Verify the current literal tuple
  equals the derived set before switching (it should; if not, report the
  difference rather than silently changing `loom generate` routing).
- Drift guard test: both consumers equal `model_file_suffixes()` (plus
  `.zip` for the scanner).
- Behaviour tests: a SentencePiece-shaped `.model` (protobuf bytes, e.g.
  `b"\n\x0f"` plus filler) in a project scan logs nothing at `INFO` or
  above and lists no model; `loom model x.model` on it refuses with the
  existing "not an AI model file of a supported format" message;
  `loom generate x.model` routes to the model branch for a CRFsuite file.

## Step 6: surface tests (M)

Per AGENTS.md "a test asserting on one surface doesn't cover the others":

- `tests/assemble/test_model_outcome_parity.py`: add CRFsuite kinds
  (good, hostile) if it enumerates formats; otherwise one parametrised test
  that the project scan, wheel scan and `loom model` give the same entry,
  name (`complete`), type and description for `complete.crfsuite`, and the
  same single `WARNING:` for a truncated copy.
- Wheel scan: CRFsuite is read inside wheels without
  `--trust-wheel-model` (not gated).
- Determinism: two `loom project` runs over a project holding both
  fixtures give identical bytes.

## Step 7: docs, skills, plugin (S)

Update, in British English, each with `Last-Modified` where it has one:

- `docs/ai-model-formats.md` (supported formats table);
- `docs/ai-model-scan-limits.md`: `loom generate` suffix list, candidate
  suffixes (`.model` shared, magic required), "header that confirms"
  table (`lCRF` at 0), fields a format never carries (name, version,
  licence for CRFsuite), limits (label count, labels chunk bytes);
- `README.md` and `docs/index.md` format lists, `docs/cli.md` if it lists
  suffixes;
- `skills/sbom-generate/SKILL.md` description (the only trigger) and
  `references/known-limitations.md`; `.claude-plugin/plugin.json`
  keywords;
- `CHANGELOG.md` `### Added`: one bullet, about 160 characters;
- `working-docs/design/crfsuite-support.md`: status to "built in #N",
  then move decisions to `working-docs/implementation/` per AGENTS.md;
  trim the roadmap bullet.

Grep for every place listing formats (`grep -rn "fastText" docs README.md
skills .claude-plugin`) rather than trusting this list.

## Step 8: review loop and real-file check (L)

Repeat until a round finds nothing above cleanup: code review of the whole
diff, fix, regression test per fix, full suite, all linters (pyrefly
included), mutation testing of `formats/crfsuite.py` and the adapter
(mutants: each check in the step 2 table removed or off by one, `ksize`
without the `- 1`, chunk-relative offset made file-relative, label order
sorted, `header.num_features` used instead of `FEAT.num`), and the manual
CLI checks (`--only '15,17,M/model/*'`, then the full run).

Real files (manual, not committed): `loom project
/Users/arthit/projects/pythainlp` lists five CRFsuite `ai_AIPackage`s,
with the label counts in [crfsuite-support.md](crfsuite-support.md), no
`WARNING:`, and name/version/licence absent from the file as expected.

## Decisions still open (ask the user, do not decide in a step)

- `max_crfsuite_label_bytes` (1 MiB proposed; the PyThaiNLP labels chunks
  are a few KB).
