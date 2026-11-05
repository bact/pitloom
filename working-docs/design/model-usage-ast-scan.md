---
Created: 2026-10-31
Last-Modified: 2026-11-05
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Model usage scan: read what the code does with the file

See also: [roadmap.md](roadmap.md) (the summary bullet),
[ml-framework-from-code.md](ml-framework-from-code.md) (the sibling idea:
which framework loads a model),
[message-catalogue-and-skills.md](message-catalogue-and-skills.md) (the codes
used below) and, for what exists today,
`src/pitloom/extract/scanner.py` (`attach_usage_references`).

Status: built 2026-10-31 (`core/model_usage.py`, `extract/_usage_table.py`,
`extract/_usage_match.py`, `extract/_usage_ast.py`, `extract/_usage_attach.py`,
`messages/_usage_unparseable.py`). The sections below are the design as
decided; "Problem" describes the substring scan it replaced.

## Problem

`--scan-model-usage` / `scan-model-usage = true` records a `hasDataFile`
relationship from a `.py` file to a model file when the model's **file name
appears as a substring** of the Python text. That gives false positives:

- the name in a comment, a docstring, a log or exception message;
- the name as part of another word (`big_a.onnx` matches `a.onnx`);
- two models with one file name in different directories (both match);

and says nothing about *how* the code uses the file.

## Decisions

Decided with the maintainer on 2026-10-31. Rationale in brackets.

1. **Replace the substring scan with an AST scan.** Not a second mode.
   [The goal is fewer false positives; a mode that keeps the old
   behaviour keeps them.]
2. **Output: the existing `hasDataFile` edge, with the access in the
   relationship `comment`.** Fixed vocabulary, kept as constants:
   `read access`, `write access`, `read and write access`, `unknown access`.
3. **`unknown access`**: the code passes the model's path to something that
   is neither a known reader nor a known writer. It is an edge, with that
   comment.
4. **Mention-only uses give no edge**: the path as an argument to `print`,
   logging calls, an exception message, a comment, a docstring.
5. **Lifecycle scope stays as it is today (`runtime`) for every edge.**
   [Opening a file carries no intention, unlike the `loom` decorator: a script
   may write a model while developing. Pitloom cannot tell, so it does not
   claim `development` for a write.]
6. **A match to several models gives an edge to each.**
7. **A method-name-only match counts** (`obj.save_model(p)`, `obj.load(p)`):
   it is classified read or write from the method name, though the object's
   type is unknown. [The path literal is already a match; the method name only
   picks the access.]
8. **A file that cannot be parsed gives no relationship, only messages**:
   a `WARNING:` that it could not be parsed, and an `INFO:` that a model file
   name was found in it but no relationship was recorded. The text is searched
   only to say that; it is never a claim.

## Design

### Pipeline

1. Discover models (unchanged, always runs).
2. For each `.py` source, in sorted path order (unchanged):
   1. Read at most 1 MiB, strict UTF-8 (unchanged; a BOM is stripped first,
      as `ast.parse` rejects `U+FEFF` in a `str`).
   2. **Pre-filter:** continue only when the text contains the file name of at
      least one model. Most files are never parsed.
   3. `ast.parse` the text. On failure, see "Parse failures".
   4. Walk the tree and classify each path-shaped constant that matches a
      model (see "Matching" and "Classification").
3. Keep one entry per (`.py`, model) pair, its access merged
   (read + write = `read and write access`; `unknown access` only when no
   classified access exists for the pair).

### Data model

`AiModelMetadata.usage_files: list[str]` becomes a list of a small frozen
dataclass `ModelUsage(distribution_path, access)`, `access` one of a closed
`Enum`. The list stays sorted by distribution path and deduplicated by the
pair. `assemble/spdx3/ai.py` (`_add_ai_model_file_relationships`) writes the
`comment`, from the same constants. Every constructor site of the field is
updated (tests in `tests/extract/scanner/`, `tests/assemble/` and
`tests/core/generator/` build it directly).

### Matching

A string constant counts only when it is **path-shaped**: it equals the model's
file name, or ends in `/<name>` or `\<name>` (the Windows spelling). Then
`"Saved model.ftz to disk"` is no match, and `big_a.onnx` no longer matches
`a.onnx`.

With the literal's directory parts known, require them to be a suffix of the
model's distribution path or physical path (`"data/model.ftz"` matches only a
model under `.../data/`). A bare file name still matches every model of that
name (decision 6).

Skip bare expression statements (including docstrings, which are `ast.Expr`
nodes holding a string constant) explicitly. Comments are not in the AST and
need no skipping.

Constant resolution, within **one file** only:

- a module- or function-level `NAME = "..."` read back as a `Name`;
- `Path("a") / "b"`, `os.path.join("a", "b")`, `PurePosixPath(...)`, with
  literal parts;
- f-strings and `"..." % ...` / `.format()` with constant or partially
  constant parts (bounded to depth 64 and 4,096 characters; an expression
  over either is not followed at all, so a capped operand never leaves a bare
  tail that matches). `.format` fields with an attribute, index, conversion
  other than `!s` or a spec, a bare `%s` only, `%%`/`{{` escapes, `%(name)s`
  with a dict, and positions after a `*iterable` are handled; `**mapping` and
  `*iterable` arguments leave their values unknown. In a `%` dict, a key
  before a `**d` or a computed key may be replaced at run time, so its value
  is unknown too; a string literal holding a NUL is no path (`open` raises).
- a path rendered into a string (`f"{p!r}"`, `f"{p:>30}"`) is no longer the
  path: a mention call (`print`, `log.info`, `raise`) gives no edge, any
  other consumer gives `unknown access`.

Decided losses (each was `unknown access` before the AST fix round): an
unknown template or receiver (`tmpl.format("data/model.ftz")`,
`base % "model.ftz"`) and `"data/model.ftz" + ext` give no edge, since the
file named is `model.ftz<ext>` or unknown; `os.path.join(unknown,
"model.ftz")` still matches, as a join keeps its last part whole. A model at
the project root matches a rooted `/model.ftz`, `~/model.ftz` or
`C:\model.ftz` but not the checkout's own absolute path.

Limits of the name and call tables, found in review and left as they are:

- **Bindings are counted per file, not per scope.** A name bound once in the
  whole file is a constant; `path` reused in two functions, or a `for`, `with`
  or `except` target of the same name elsewhere, makes it none, and the model
  then gets `unknown access` (the edge is kept, the detail lost). A constant
  read inside a function defined above it is also unknown (source order, not
  run order), and a star import can hide that a name is not the file's own.
  Real scope tracking (`symtable`) is the fix, as its own piece of work.
- **Import aliases are per file too**: a local `def store` beside
  `from torch import save as store` reads as `torch.save`.
- **A callee is known by its last name**, so a mode means what stdio's `open`
  means: `"a"` is a write for `h5py.File` and `zipfile.ZipFile`, which also
  read the file; `shelve.open` and `zarr.open` default to read-write; the long
  `np.memmap` modes are unknown. `f.write(path)` and `json.dump(path, f)` put
  the path in a data position, so they are unknown, as is `zf.write(path)`
  (which reads it).
- **`.PY`** is not scanned: Python's import rules accept only `.py`. With a
  model found, each such file is warned of once (`[usage-unusable]`).

Out of scope for the first version: values imported from another module,
`**kwargs`, `getattr`, config files, notebooks. The docs keep saying
"best effort".

### Classification

A table of callables, matched by the last name of the callee after resolving
`import x as y` and `from x import y`, giving the access (and for `MODE_CALLS`,
the position of the `mode` argument). The path is not matched by argument
position: `torch.save(obj, path)` and `joblib.dump(obj, path)` take it second,
`np.save(path, arr)` first; the path-shaped argument naming a model is the one
classified.

| Access | Callables (first version) |
| :--- | :--- |
| read | `open(p)` and mode `r`/`rb`/`rt`, `Path(p).read_text/read_bytes`, `joblib.load`, `pickle.load` (via an open file: the `open()` is the match), `torch.load`, `np.load`, `onnx.load`, `onnxruntime.InferenceSession`, `fasttext.load_model`, `safetensors.*.load_file`, `keras.models.load_model`, `h5py.File(p)` and mode `r`, `AutoModel*.from_pretrained` |
| write | `open(p)` with mode `w`/`wb`/`wt`/`a`/`x`, `Path(p).write_text/write_bytes`, `joblib.dump`, `torch.save`, `np.save`, `onnx.save`, `*.save_model`, `safetensors.*.save_file`, `h5py.File(p)` and mode `w`/`a` |
| read and write | `open(p)` with mode containing `+`; `h5py.File(p)` mode `r+` |
| method-name only (decision 7) | `.load*`, `.read*` give read; `.save*`, `.write*`, `.dump*` give write; on an object whose type is unknown |
| unknown | the path is an argument of any other call, or assigned and never used by a known call |
| no edge | argument of `print`, a `logging` call or `Logger` method, an `Exception(...)` or `raise`, `assert` messages, `warnings.warn` |

A non-constant `open()` mode is `unknown access`. The table lives in one
module (`extract/_usage_table.py`), data not code, so a library is added in one
place; the doc lists it as the source of truth. A call not in the table is
never an error.

### Parse failures

`ast.parse` can fail for reasons that are not the file's fault, so the message
must not say the file is broken:

- `SyntaxError`: also **valid code the build's Python does not know**
  (`except*` before 3.11, `type X = ...` before 3.12, PEP 701 f-strings before
  3.12, `match` before 3.10).
- `ValueError`: a null byte (Python 3.10 and 3.11; 3.12 raises `SyntaxError`).
- `MemoryError`: "Parser stack overflowed" on deeply nested source (seen on
  3.10 with 200,000 unary operators).
- `RecursionError`: a deeply nested tree in the walk or the compiler.

Catch all four (and no broader), per file. Do not let one file stop the scan.
`DeprecationWarning` / `SyntaxWarning` from an invalid escape such as
`"data\model.ftz"` (a Windows path, the likely literal) is **not** a failure:
wrap the call in `warnings.catch_warnings()` with `simplefilter("ignore")` so
the user's warning filters do not turn it into one, and nothing is printed.

Consequence for determinism: the SBOM can differ by the Python that built it
(a file one interpreter parses and another does not). That is a changed
environment, allowed by the output rules, and the docs state it. The warning
names the interpreter version.

Messages, new catalogue entries (one data point per line):

```text
WARNING: FILE=<file>: could not parse as Python <x.y> for usage scanning; <failure> [usage-unparseable]
INFO: FILE=<file> MODEL=<name>: model file name found; no usage relationship recorded [usage-unparseable/mention]
```

- One `WARNING:` per unparseable file that mentions a model; one `INFO:` per
  (file, model) pair. The pre-filter means an unparseable file that mentions no
  model stays silent (cookiecutter templates, Python 2 scripts, deliberate
  fixtures): *absent data is not an error*.
- `condition`: a new `unparseable` entry in `CONDITIONS`; `effect` `thinner`;
  `actor` `user`. The advice says: fix or exclude the file, or run the build
  with a newer Python, and generate again; do not edit for them. Say the
  failure through the `failure` field (`one_line`), never the exception text.
- `use` stays `for usage scanning` (already in `READ_USES`).
- Update, in the same change: `_catalogue.py`, the generated reference
  (`scripts/generate_message_reference.py`), `docs/message-codes.md` and any
  `skills/*/SKILL.md` that quotes usage-scan output;
  `tests/messages/test_drift_*.py` must pass.
- The existing `file-unreadable` and `file-unreadable/not-utf8` lines for the
  1 MiB cap and the encoding stay as they are.

### Untrusted input

Source files are attacker text. `ast.parse` does not execute code, and the 1
MiB cap bounds its cost, but parse depth and memory are bounded only by the
catches above. Never `eval`, `compile` to run, or import the file. Paths in
messages go through `loggable()` / the catalogue's fields.

## Work breakdown

1. `extract/_usage_table.py`: the callable table and the mode rules.
2. `extract/_usage_match.py` and `extract/_usage_ast.py`: path/suffix matching
   and the AST visitor (constants, alias resolution, mention exclusion,
   classification); no I/O.
3. `extract/_usage_attach.py` and `extract/scanner.py`: `attach_usage_references`
   calls `attach_from_source`; the pre-filter, failure handling and the two
   messages stay in the I/O/attachment layer.
4. `core/model_usage.py` and `core/ai_metadata.py`: `ModelUsage`, `UsageAccess`;
   migrate `usage_files`.
5. `assemble/spdx3/ai.py`: the `comment` on `hasDataFile`.
6. Messages: `usage-unparseable` family and its variant; reference regenerated.
7. Docs: `docs/ai-model-scan-limits.md` (the "Usage edges" paragraph: no longer
   "file name as text"; the new limits), `docs/ai-model-formats.md`,
   `docs/message-codes.md` and `skills/*/references/messages.md`.
8. `CHANGELOG.md`: output changes for existing projects (`hasDataFile` edges
   gain a comment; some edges disappear). Linked [#413].
9. Field note: the false-positive reduction, with a before/after count on the
   sentimentdemo project and mistral-inference.

## Tests

- **Pure visitor**, parametrised, with short `ids=`: each row of the table; a
  mode that is not constant; `import x as y` and `from x import y`; the
  matching rules (path-shaped, suffix directories, `big_a.onnx` vs `a.onnx`,
  Windows separator); docstring, comment, log, `print`, `raise` give no edge;
  f-string and `Path /` resolution; a read and a write in one file give one
  `read and write access` edge; two models with one name give two edges.
- **Parse failures:** each of `SyntaxError`, null byte, deep nesting
  (`MemoryError`), `RecursionError`: one `WARNING:` and the `INFO:`; no edge;
  later files still scanned; silence when no model name is in the file;
  version-gated syntax is tested by mocking `ast.parse` where the real
  interpreter accepts it.
- **Warnings:** an invalid-escape literal is accepted, prints nothing, even
  under `-W error`.
- **Both determinism legs:** two runs give identical bytes; the SBOM validates
  against SPDX 3 (`spdx3-validate`).
- **Every surface,** per the usage-surfaces rule: CLI (`project`, `wheel`),
  the Hatchling hook (`scan-model-usage = true` in `[tool.pitloom]`), the
  library (`scan_model_usage=`), `embed-wheel` with and without
  `--project-dir`. Each reaches `scan_ai_models`; test each's output, not one.
- **Windows dry run:** `\` in a literal and in an expected path, `PureWindowsPath`.
- **Mutation testing** on `A and B` rules (path-shaped and suffix match; read
  mode and mode `+`).
- **Message drift:** `tests/messages/` as above; the quote tests for docs and
  skills.

## Open points

- Whether `hasDataFile` (from a script to a model) is the best relationship
  type for a write. SPDX 3 has no read/write relationship; `generates` or
  `hasInput` model it more exactly but claim intention (decision 5). Record the
  mismatch in `sbom-format-gaps.md`.
- `loom.set_model()` / `use_model()` in the same file say what the code
  means. A later step could prefer them to the AST guess for a model declared
  with `path=`. Not in this change.
- Notebooks (`.ipynb`) stay out; revisit with
  [ml-framework-from-code.md](ml-framework-from-code.md).
- The first table is a seed. Extend from a corpus, not from memory: list the
  callables that take a model path in the repositories of
  `working-docs/design/ai-model-corpus.md`.
