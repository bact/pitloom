---
Created: 2026-10-15
Last-Modified: 2026-10-15
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Metadata provenance: preserved artifact metadata

See also: [Metadata provenance](metadata-provenance.md) for the
provenance annotations and the `method` values, [Reading
values back](metadata-reading-back.md) for the order to undo these
layers, and the other parts: [Licences and
copyright](metadata-provenance-licences.md),
[Authors](metadata-provenance-authors.md).

## Preserved artifact metadata

`preserve-source-metadata` embeds an artifact's own metadata in one
`Annotation.statement` of kind `artifact-metadata`, keyed as the file
names it. The rule is the same for every model format:

- a collection in the file (a label list, an archive listing, a metrics
  list) is a JSON array, or a JSON object where the file has a mapping;
- a scalar is text: the same text as in the model's properties and in
  its `ai_hyperparameter` values, where a value appears there. A number
  or boolean is never a JSON number or boolean, since a JSON consumer may
  widen or round it (an integer above 2^53);
- the text of a scalar has one spelling: a boolean `true` or `false`; an
  integer in decimal, up to 640 digits (a longer one is
  `<integer of N bits>`, N its bit length, and has no `valueTypes`
  entry); a float in the
  [RFC 8785](https://www.rfc-editor.org/rfc/rfc8785) (ECMAScript)
  spelling, the shortest decimal that reads back as the same double
  (`0.00001`, `1e-7`, `100`, `1e+21`); NaN and the infinities, which RFC
  8785 has no spelling for, `NaN`, `INF` and `-INF` (the XSD `double`
  spellings). `-0.0` is `0`, as in RFC 8785: the value is equal, only the
  sign of the zero is lost;
- a GGUF `FLOAT32` value is spelt as the float32's own shortest decimal,
  not as the double it widens to: a stored `1e-5` is `0.00001`, not
  `9.999999747378752e-06`. The text reads back as the same float32. A
  `FLOAT64` value keeps its own spelling. Only GGUF declares a value
  float32; another format's float is spelt as the double it reads as;
- `valueTypes` maps each top-level `metadata` key whose value is a
  non-string scalar in the source to `integer`, `float` or `boolean`, so a
  consumer can read the text back as its type without knowing the format.
  A key not in it is a string, a collection or a GGUF array summary.
  `valueTypes` is left out when no key has a type;
- collection elements are text too, spelt the same way (`null` for a
  missing value): `true`, `false`, `null`, `1`, `0.5` (an HDF5 metric
  `{"acc": true}` is `{"acc": "true"}`; a PT2 tag `null` is `"null"`).
  Elements are not typed;
- a key the file holds no value for is left out, never `null`;
- a collection nested over 32 levels keeps its first 32 levels; the part
  below is its JSON text (or `<nested over 32 levels>` where even that
  nests too deeply), so a hostile nesting never stops the model being read;
- a GGUF array is a summary object of text, `{"length": "N", "type":
  "<element type>"}`, never its elements;
- text is kept as the file holds it, bidi and zero-width controls
  included: the annotation is data, its values JSON strings for a program
  to read. The properties shown to a reader have those controls escaped
  instead (see [Reading values back](metadata-reading-back.md)).

A fastText classifier:

```json
{
  "format": "fasttext",
  "kind": "artifact-metadata",
  "metadata": {
    "labels": ["__label__q", "__label__pos", "__label__neu", "__label__neg"],
    "lossName": "softmax"
  },
  "schema": "https://pitloom.dev/provenance/artifact-metadata/2"
}
```

A CRFsuite tagger:

```json
{
  "format": "crfsuite",
  "kind": "artifact-metadata",
  "metadata": {
    "labels": ["I", "E"],
    "model_type": "FOMC",
    "num_attributes": "2",
    "num_features": "4",
    "num_labels": "2"
  },
  "schema": "https://pitloom.dev/provenance/artifact-metadata/2",
  "valueTypes": {
    "num_attributes": "integer",
    "num_features": "integer",
    "num_labels": "integer"
  }
}
```

A GGUF model (`stories260K.gguf`, some keys left out here), whose
`llama.attention.layer_norm_rms_epsilon` is the `ai_hyperparameter` value
`0.00001` too:

```json
{
  "format": "gguf",
  "kind": "artifact-metadata",
  "metadata": {
    "general.architecture": "llama",
    "llama.attention.layer_norm_rms_epsilon": "0.00001",
    "llama.block_count": "5",
    "tokenizer.ggml.model": "llama",
    "tokenizer.ggml.tokens": {"length": "512", "type": "STRING"}
  },
  "schema": "https://pitloom.dev/provenance/artifact-metadata/2",
  "valueTypes": {
    "llama.attention.layer_norm_rms_epsilon": "float",
    "llama.block_count": "integer"
  }
}
```

A Hugging Face model, which is no model file, follows the same rules
(`"format": "huggingface"`): its Hub and `config.json` scalars are text,
typed in `valueTypes`, its lists and objects arrays and objects.

An archive listing (`archive_contents` of a PyTorch or PT2 archive) holds
the first 20 member names, the same ones the property text shows;
`archive_member_count` beside it is the number of members in the archive.

## Size-bounded preservation

`preserve-source-metadata` can embed an artifact's verbatim original
metadata (e.g. a GGUF model's key/value header) into a single
`Annotation.statement`. For a real model this can be large -- a chat
template alone can be several KiB. `max-source-metadata-bytes` caps the
serialised `Annotation.statement`'s size in UTF-8 bytes; `0` (the default)
means unlimited. Valid values and its flag, Action input and API parameter:
[Configuration](configuration.md#toolpitloomprovenance).

When the budget is exceeded, whole metadata entries are dropped --
largest first, to keep as many entries as possible -- never a value
truncated mid-string, which would produce invalid JSON. A dropped key's
`valueTypes` entry goes with it. The reduction is
always marked explicitly in the same envelope, never silent:

```json
{
  "format": "gguf",
  "kind": "artifact-metadata",
  "maxMetadataBytes": 500,
  "metadata": {"general.architecture": "llama", "llama.block_count": "32"},
  "schema": "https://pitloom.dev/provenance/artifact-metadata/2",
  "truncated": true,
  "truncatedKeyCount": 1,
  "truncatedKeys": ["tokenizer.chat_template"],
  "valueTypes": {"llama.block_count": "integer"}
}
```

If the budget is too small to hold even an empty `metadata: {}` plus the
marker fields, no Annotation is emitted for that artifact at all (a
`WARNING` is logged) -- an Annotation whose own `maxMetadataBytes` field
claims a budget its own overhead violates would be worse than omitting
it. A budget that forces every key to be dropped, but still fits the
marker overhead, is emitted with `metadata: {}` and a `WARNING`.

A model file with more than 1000 metadata keys keeps its first 1000 (the
[entry cap](ai-model-scan-limits.md#size-and-count-caps)). The keys left
out are counted, not named -- listing them would cost what the cap saves
-- and `maxEntries` names the cap. For a Safetensors model of 1500
`__metadata__` keys (its 1000 kept keys left out here):

```json
{
  "maxEntries": 1000,
  "truncated": true,
  "truncatedKeyCount": 500
}
```

When the byte budget drops keys from the same annotation, `truncatedKeys`
and `maxMetadataBytes` are added and `truncatedKeyCount` counts both: the
keys named in `truncatedKeys` and those over `maxEntries`.

Every JSON text Pitloom writes -- each `Annotation.statement`,
`ai_informationAboutApplication`, and the text of a model property holding
a list or an object (fastText and CRFsuite `labels`, HDF5
`loss`/`metrics`) -- is serialised via RFC 8785 (JSON Canonicalization
Scheme, JCS), the same canonicalisation the whole SBOM document uses: no
insignificant whitespace and a deterministic key order, so byte-for-byte
comparing or hashing it across runs with unchanged input is safe. A value
RFC 8785 has no spelling for is a string in it: NaN and the infinities
`NaN`, `INF` and `-INF`, an integer beyond +-(2^53 - 1) its full decimal
text.
