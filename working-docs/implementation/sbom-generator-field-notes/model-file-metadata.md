---
Created: 2026-10-08
Last-Modified: 2026-10-08
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Field notes: model-file metadata

See also: [README.md](README.md) (index of these notes),
[remote-metadata.md](remote-metadata.md) (the same question for package
metadata), [spdx-modelling.md](spdx-modelling.md),
[ai-model-scan-security-lessons.md](../ai-model-scan-security-lessons.md)
(hostile model files).

What AI model files actually carry in their metadata fields, and what those
fields mean, measured on the ONNX fixtures under `tests/fixtures/aimodels/`
and the three ONNX models bundled with PyThaiNLP 5.3.9 (`deepcut.onnx`,
`thai2rom_encoder.onnx`, `thai2rom_decoder.onnx`). All items from #292.

- **A field name shared with SPDX can mean something else.** ONNX
  `ModelProto.domain` is "a reverse-DNS name to indicate the model
  namespace or domain, for example, 'org.onnx'", and the IR spec says
  models SHOULD set it from "the responsible organization's identity": it
  names an owner. Pitloom mapped it to SPDX `ai_typeOfModel`, so a model
  stamped `org.pythainlp` would have been typed `org.pythainlp`; a mocked
  test asserted `domain="ai.onnx"` gives type `ai.onnx`, pinning the
  misreading. "Domain" means three things here: the ONNX owner namespace,
  an ONNX opset domain (`ai.onnx`, `com.microsoft`: an operator set), and
  SPDX `ai_domain` (the field of application, such as NLP). Every real
  fixture had an empty `domain`, so no end-to-end test could notice.
  Do: map a format field by its spec definition, never by its name; cite
  the definition next to the mapping; give a test fixture a realistic
  non-empty value for every field the mapping reads.
- **The model name is often the exporter's, not the model's.**
  `graph.name` is required, so exporters fill it. Observed by
  `producer_version`: `torch-jit-export` from PyTorch 1.8 (both thai2rom
  files), `torch_jit` from 1.12.0 and 1.13.1 (two fixtures), `main_graph`
  from 2.6.0 (the Whisper encoder fixture), `tf2onnx` from tf2onnx 1.12.0
  (`deepcut.onnx`). Read as a name, PyThaiNLP's SBOM listed two different
  models both called `torch-jit-export`.
  Do: treat known exporter defaults as no name; fall back to the file
  name stem and record that it was derived.
- **An integer version can be packed SemVer.** `model_version` is an
  int64. The versioning doc packs SemVer as MAJOR (16 bits), MINOR (16),
  PATCH (32); non-zero upper 32 bits mark SemVer, zero marks a simple
  number. `1.0.0` is stored as 281474976710656, which a plain `str()` puts
  in the SBOM as the version. `0.0.x` cannot be expressed as SemVer. The
  packing rule is a MUST; using SemVer for models at all is only a
  recommended convention (the spec requires no scheme).
  Do: decode by the format's own rule and record the decoding in
  provenance (`Method: semver_bit_packed`).
- **Standard metadata keys exist, but exporters leave them empty.** The
  IR spec defines two `metadata_props` keys, `model_author` and
  `model_license` ("name or URL", not an SPDX expression). Neither
  `torch.onnx.export` nor tf2onnx sets them, nor `model_version` or
  `doc_string`: all three PyThaiNLP files had no metadata properties,
  version 0 and an empty description, while the licences, authors and
  versions sat in PyThaiNLP's own `default_db.json` catalogue. A licence
  name (`MIT License`) or URL stays licence text, not an SPDX id
  ([license-rules.md](../../design/license-rules.md) open questions 11 and
  17).
  Do: read the standard keys only; expect them absent; point model owners
  at the spec's keys and fields instead of a generator-specific format.
