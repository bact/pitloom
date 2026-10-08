---
Created: 2026-10-08
Last-Modified: 2026-10-08
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Reading values back

See also: [Metadata provenance](metadata-provenance.md) for the
artifact-metadata annotation, and [AI model scan
limits](ai-model-scan-limits.md#size-and-count-caps) for every cap.

A value read from a model file or a Hugging Face card passes through
several layers before it is in the SBOM. This page lists them in the order
Pitloom applies them, and the order a program reading the SBOM undoes them.

## Layers, in write order

1. **Read.** The value is read from the file (or the Hub) as it is. A
   lone surrogate (U+D800 to U+DFFF, which a JSON or YAML `"\ud800"`
   escape gives) cannot be written as UTF-8, so it is written as the six
   characters `\udXXX` here, with one `WARNING: FORMAT=<fmt> FILE=<path>:
   lone surrogates written as \uXXXX`; the annotation holds that text too.
2. **Caps.** A name over 1024 characters (a model's, its base model's, a
   dataset's or a dataset creator's) is cut to its first 1012, `...`, `~`
   and 8 hex digits of the SHA-256 of the whole name, so two long names
   stay apart; a label over 4096 bytes means no label is recorded; a list
   or map keeps its first 1000 entries; `max-source-metadata-bytes` drops
   whole annotation entries. Each is announced by a `WARNING:` and, in the
   annotation, by `truncated`, `truncatedKeyCount`, `truncatedKeys`,
   `maxEntries` or `maxMetadataBytes`
   ([size-bounded preservation](metadata-provenance.md#size-bounded-preservation)).
   Caps come before the escape, so an escaped value can be longer than
   its cap: each escaped code point adds five characters.
3. **Scalar text.** A number or boolean is text with one spelling: `true`,
   `false`, a decimal integer, a float in RFC 8785 spelling, `NaN`, `INF`,
   `-INF`; `-0.0` is `0`. In the annotation, `valueTypes` names each
   top-level key whose value was an `integer`, `float` or `boolean`
   ([preserved artifact metadata](metadata-provenance.md#preserved-artifact-metadata)).
4. **Display escape.** In the elements shown to a reader, each code point
   a reader cannot see, or that changes how the text around it is shown,
   is written as the six characters `\uXXXX`, in lowercase hex (`\u202e`),
   so U+202E cannot turn `txt.exe` into `exe.txt` on screen: the C0
   controls but TAB, LF and CR, DEL and the C1 controls (U+007F to
   U+009F), U+00AD, U+034F, U+061C, U+180E, U+200B to U+200F, U+2028,
   U+2029, U+202A to U+202E, U+2060 to U+2064, U+2066 to U+206F, U+FEFF,
   U+FFF9 to U+FFFB, and the tag characters U+E0000 to U+E007F (written as
   their UTF-16 surrogate pair, `\udb40\udc41`, as JSON spells them). A URL
   is percent-encoded instead (`%E2%80%AE`), and an `spdxId` is minted
   from the text before this step, with the same code points
   percent-encoded. The escaped properties: a model's `name`, `summary`,
   `description`, `comment`, `software_packageVersion`,
   `software_downloadLocation` (percent-encoded), `ai_limitation`,
   `ai_typeOfModel`, `ai_domain`, `ai_hyperparameter` keys and values,
   the strings in `ai_informationAboutApplication`, `externalRef` and
   `externalIdentifier` text and locators; the same properties of the
   base-model package, the dataset packages and their creators the model
   brings in, with a dataset's `dataset_dataCollectionProcess`,
   `dataset_intendedUse`, `dataset_dataPreprocessing`,
   `dataset_knownBias` and `dataset_anonymizationMethodUsed`; the
   `name`, `simplelicensing_licenseText` and
   `simplelicensing_licenseExpression` of the model's licence element;
   and the comments of their relationships. One `WARNING: FORMAT=<fmt>
   FILE=<path>: invisible or bidi control characters written as \uXXXX in
   <properties>` per model names them. Provenance text quoting a file or
   key name (`Source:`, `Field:`) is escaped the same way, but not yet a
   key name in a provenance annotation's `fields` object, nor an
   enrichment annotation's `changes` (`field`, `after`), which keep the
   text as read. In the provenance `comment`, `;`, CR and LF in a field or
   source, and `:` in a field, are written as `\u003b`, `\u000d`,
   `\u000a` and `\u003a`, so a key cannot forge an entry. The
   artifact-metadata annotation is not escaped: it keeps the text as read.
5. **JSON.** Each embedded JSON text (an `Annotation.statement`,
   `ai_informationAboutApplication`, a property holding a list) is written
   with RFC 8785 (JCS), then the SBOM itself is, too (`--pretty` indents
   it instead). JCS escapes only `"`, `\` and the C0 controls U+0000 to
   U+001F; every other character, U+202E included, is written as UTF-8.
   The backslash of a step 4 escape is therefore `\\` in the file. Keys
   read from a model are never JSON key names of the SBOM: they are
   `DictionaryEntry.key` values, or keys inside an embedded JSON text.

| Layer | Where | Reversible? | How to undo |
| :---- | :---- | :---------- | :---------- |
| Caps | Name, labels, lists, annotation | No | Read the file |
| Scalar text | Properties, `ai_hyperparameter`, annotation | Yes, by type | `valueTypes` |
| Display escape | Display properties, URLs | No (see below) | Read the annotation `metadata` |
| JSON (RFC 8785) | Embedded JSON texts, the SBOM | Yes | Any JSON parser |

## Reading order

1. JSON-decode the SBOM: standard JSON, nothing Pitloom-specific.
2. JSON-decode the string of each property known to hold JSON (an
   `Annotation` with `contentType` `application/json`,
   `ai_informationAboutApplication`). RFC 8785 output is plain JSON.
3. Type the annotation's scalar texts with its `valueTypes`: a key not in
   it is a string, a collection or a GGUF array summary. Elements inside a
   collection are text too, and not typed.
4. Do not undo the display escape. A `\u202e` the file already held as six
   characters looks the same as an escaped U+202E, so the escape cannot be
   reversed with certainty. For the original, read the annotation's
   `metadata` where the format keeps the field there (an ONNX graph or
   input name is not kept), or the file. To render a display value
   anyway, replace `\uXXXX` for exactly the code points listed in step 4
   above, and treat the result as untrusted text. A `\udXXX` from step 1
   has no original in the SBOM.
5. Caps are one-way. A name ending `...~` and 8 hex digits with its
   `WARNING:`, an annotation marked `truncated`, or labels absent after
   the over-cap `WARNING:` mean the full value is only in the file.

## Example

A GGUF model whose `general.name` holds U+202E, with
`loom model demo.gguf`. Its `ai_AIPackage` (excerpt):

```json
{
  "name": "evil\\u202etxt.exe",
  "ai_hyperparameter": [
    {"key": "llama.context_length", "type": "DictionaryEntry", "value": "4096"}
  ]
}
```

Its artifact-metadata annotation's `statement`, once decoded (excerpt;
shown with JSON's own escape, the SBOM holds U+202E itself):

```json
{
  "metadata": {"general.name": "evil\u202etxt.exe", "llama.context_length": "4096"},
  "valueTypes": {"llama.context_length": "integer"}
}
```

Decoded, `name` is `evil\u202etxt.exe` with a literal backslash, safe
to print; the annotation gives the original name, with U+202E, and `4096`
typed as an integer.
