---
Created: 2026-10-08
Last-Modified: 2026-10-08
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# One spelling for scalar text (option D)

Status: built in #294 (decided 2026-10-08). Follows the value-type rule
decided in #294 (collections are arrays, scalars are text; see
[annotation-mechanism.md](provenance/annotation-mechanism.md#value-types-in-artifact-metadata-metadata-2026-10-08),
which also records how it was built).

See also: [annotation-mechanism.md](provenance/annotation-mechanism.md),
[model-metadata-readers.md](../design/model-metadata-readers.md),
[RFC 8785](https://www.rfc-editor.org/rfc/rfc8785) (§3.1, §3.2.2.3,
Appendices B, D, E).

## Why

Before #294 a scalar became text in four places, each with its own `str()`, so
one value has up to four spellings and none is a standard:

| Sink | Where | Spelling before |
|---|---|---|
| `properties` text | readers (readers' `properties`) | Python `str()` |
| `ai_hyperparameter` value | `assemble/spdx3/_ai_package.py` | Python `str()` of a native value |
| annotation `metadata` scalar | `core/ai_metadata.py` `source_metadata_value` | Python `str()` |
| annotation collection element | same, JSON spelling | `json.dumps` |

Measured (real `rfc8785` 0.1.4, checked against RFC 8785 Appendix B, all
14 samples match):

- Python and JSON/JS differ: `True` vs `true`, `100.0` vs `100`, `1e-07`
  vs `1e-7`, `inf` vs `Infinity`.
- GGUF float32 values are widened to float64 in `_field_value`
  (`.tolist()`), so the stored `1e-6` is written `9.999999974752427e-07`
  in `properties`, in `ai_hyperparameter` (SPDX output) and in the
  annotation. Stored `0.1f` is `0.10000000149011612`.
- RFC 8785 §3.1 / Appendix D: numbers outside an IEEE-754 double MUST be
  JSON strings; the library raises on integers beyond ±(2^53−1) and on
  NaN/Infinity. The RFC defines the spelling of a *double*, not of a number
  inside a string, and says a string-held number is converted back by a
  per-property declaration (Appendix D/E).

## Which layer: SPDX tokens vs text inside strings

The SPDX 3.0.1 canonical serialization
(<https://spdx.github.io/spdx-spec/v3.0.1/serializations/>) fixes JSON
*tokens*: `true`/`false`/`null` lowercase, integers in base 10 without
leading zeros, and nothing about floating-point numbers. It governs typed
properties (an `xsd:boolean` is the token `true`). Our scalar text sits
inside *strings* (`DictionaryEntry.value` and `Annotation.statement` are
`xsd:string`), which that section does not cover. So `true`/`false` here
follows JSON and the `xsd:boolean` lexical form, not an SPDX rule; integers
in decimal match the SPDX integer rule; floats have no SPDX rule, which is
why RFC 8785 spelling is used.

## Decision (option D)

One function, `scalar_text(value)`, is the only way a scalar becomes text.

| Input | Output |
|---|---|
| `str` | as is |
| `bool` (also `numpy.bool_`) | `true` / `false` |
| integer (also `numpy.integer`) | decimal, any size |
| float (also `numpy.float64`) | the RFC 8785 / ECMAScript spelling, `rfc8785.dumps(value)` |
| NaN, +Infinity, -Infinity | `NaN`, `INF`, `-INF` (XSD spellings; the RFC has none, it makes them errors) |
| `None` | no text (the key is absent) |

`-0.0` spells `0` (decided 2026-10-08). The value is unchanged
(`-0.0 == 0.0`); only the sign bit is lost, which matters for `1/x` or
`atan2` and for nothing we do: these are provenance records, never computed
on, and a negative zero in model metadata is not expected. RFC 8785
Appendix B maps both zeros to `0` and JavaScript prints `-0` as `0`, so any
JCS tool re-spelling the same double gives the same string; `-0` (a valid
XSD double) would be a one-off. It is the one documented loss in the rule.

**float32 is de-widened at the reader, not in the spelling function.** The
GGUF reader (the only reader that sees a float32) turns a `FLOAT32` value
into the double whose shortest decimal is the float32's shortest decimal:
`float(numpy.format_float_scientific(x, unique=True))`. It is exact for a float32 round trip
(`numpy.float32(result) == x`), changes the double by under one float32
ulp, and needs no new type downstream. Result: `1e-6` is written
`0.000001`, `0.1f` is `0.1`, in all three sinks.

**Read-back is declared, not guessed** (RFC 8785 Appendix D/E: a
string-held number is "pure" text, converted by a declaration per
property). The annotation schema moves to `artifact-metadata/2`:

- the envelope states the text rules above;
- the envelope gains `valueTypes` (decided 2026-10-08): an object mapping
  each top-level `metadata` key whose value is a non-string scalar to
  `integer`, `float` or `boolean`; keys absent from it are plain strings.
  Three names only (the spelling is exact, so width is not needed); a
  consumer types the text without knowing the format. It is emitted only
  when non-empty, sorted by key, and covers top-level scalars: elements
  inside a collection keep their JSON spelling (`true`, `1`) and are not
  typed. The reader supplies the type because only it still holds the
  native value (`source_metadata` receives native values for typed keys).

## Surface x member matrix

Every surface (CLI `project`/`model`/`wheel`/`generate`/`enrich`, library
API, Hatchling hook, GitHub Action) reaches the readers and the assembler
through the same code, so `scalar_text` is called at three shared points
and no surface changes:

| Format | `properties` text | `ai_hyperparameter` | annotation scalar / element | Notes |
|---|---|---|---|---|
| GGUF | `scalar_text` | `scalar_text` | `scalar_text` | float32 de-widened; bools become `true`/`false` |
| fastText | strings only | `scalar_text` (floats from the C++ binding) | `scalar_text` | `lr`/`t` are C++ doubles, nothing narrowed |
| Keras / HDF5 | `scalar_text` | `scalar_text` | `scalar_text` | `layer_count` int |
| ONNX | opset ints | -- | `scalar_text` | `metadata_props` are strings |
| PyTorch, PT2, NumPy | strings / ints | -- | `scalar_text` | |
| Safetensors | strings | -- | strings | file stores text |
| CRFsuite | counts | -- | `scalar_text` | |
| Hugging Face (`extra_data`) | -- | -- | `scalar_text` | not a model file; same `source_metadata` path |

## Traps

- `bool` is an `int` subclass: test `bool` first.
- `numpy.float32` is not a `float`: convert before `rfc8785.dumps`;
  `numpy.integer`/`numpy.bool_` are not `int`/`bool`.
- `rfc8785.dumps` raises on NaN/Infinity and on integers beyond ±(2^53−1):
  handle both before calling it; integers never go through it.
- De-widen only values the *file* declares `FLOAT32`; a stored float64 that
  happens to equal a float32 value must keep its own spelling.
- `str(numpy.float32(x))` is the shortest round-trip decimal only under
  the default print options: it follows `numpy.set_printoptions`
  (`legacy="1.13"` prints `1.0000001` as `1` and `16777216` as
  `1.67772e+07`). Use `numpy.format_float_scientific(x, unique=True)`,
  which ignores them and equals `str(x)` under the defaults (checked on
  200k random float32 values).
- Changing `True` -> `true` and float spellings changes SPDX output
  (`ai_hyperparameter`, `properties`) for existing models: ids and hashes of
  elements do not depend on them, but golden outputs do. CHANGELOG
  `### Changed`.
- `docs/` examples must be real output (the #294 review found a wrong
  fastText example).

## Decisions (2026-10-08)

- Shipped in #294, not its own PR.
- `valueTypes` is in the schema `/2` envelope, three type names.
- `-0.0` spells `0`.
