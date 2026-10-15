---
Created: 2026-10-08
Last-Modified: 2026-10-15
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
`thai2rom_encoder.onnx`, `thai2rom_decoder.onnx`). Items from #292, and from
the producer and parameter-count work
([g7-model-producer-parameter-count.md](../g7-model-producer-parameter-count.md)),
marked as such.

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
- **An ONNX opset import is not evidence of ONNX-ML operators.** tf2onnx
  adds an `ai.onnx.ml` opset import to plain neural networks, so a rule
  "ML domain imported means not a neural network" unset `type_of_model`
  for PyThaiNLP's deepcut model. Only a rule on the nodes
  (`node.domain == "ai.onnx.ml"`) was right. The fixtures never showed it
  because they were built by hand with `onnx.helper`; the PyThaiNLP
  `main` acceptance run (#294) did.
  Do: derive a model's kind from what the graph executes, not from what
  an exporter declares; test the rule on files from the real exporters.
- **No GGUF key holds a parameter count; `general.size_label` is a
  string.** The `gguf` package's `Keys.General` (0.19.0) lists
  `size_label` (text such as `7B`, a rounded label) and no
  `parameter_count`; a reader that looks for one finds
  none. The only exact figure is the sum of the elements of the
  `tensor_infos` shapes.
  A file with `split.count` above 1 holds a shard of the tensors, so its
  own sum understates the model.
  Do: derive the count from the tensor dimensions and leave a split file
  without one; never parse a size label.
- **Safetensors shapes are checked against the data offsets, so a count is
  bounded by the file size.** `safe_open` (safetensors 0.8.0) refuses a
  header whose shape disagrees with its `data_offsets` (`invalid shape,
  data type, or offset`), a negative dimension (invalid JSON for an
  unsigned integer) and a shape whose byte size overflows. Probed with a
  24-byte tensor declared `[10**6, 10**6]`, `[-1, 3]` and `[2**40, 2**40]`:
  all three refused, `[2, 3]` read. So a summed count cannot exceed what the
  file holds, apart from zero-size tensors; `get_slice(k).get_shape()`
  reads the header only.
  Do: take shapes from the library that already validated them, and cap the
  sum anyway for the formats that do not (GGUF, ONNX).
- **A product of dimensions can wrap, and an ONNX dimension can be
  negative.** The GGUF reader multiplies a tensor's dimensions with
  `numpy.prod`, which wraps: `[2**32, 2**32]` gives 0 and the reader then
  refuses the file at its own reshape, so such a tensor never reaches a
  count (`n_elements` must not be used for the count). ONNX `dims` are
  signed `int64`, so a hostile file can hold `-1` or `[10**8, 10**8]`
  without any library check. A product written with Python integers, cut at
  10**15 as soon as it passes it, is exact below the cap and cannot wrap.
  Do: multiply in Python integers, reject a negative or non-integer
  dimension, stop at a cap, and record no count (with one message) rather
  than a partial sum.
- **The Hub's default model information already carries the count.**
  `huggingface_hub`'s `model_info()` without `expand=` returns a
  `safetensors` field (`total`, `parameters` by dtype): for
  `openai-community/gpt2` `total` is 137022720, with no extra request. It
  is absent for a repository with no Safetensors metadata, and 0 can occur;
  both mean "no count stated". A GGUF-only repository has `gguf.total`
  instead (`gguf` is a plain `dict` in `huggingface_hub`'s `ModelInfo`);
  `safetensors` wins when both exist. Pitloom records either with
  `Method: tensor_element_sum`, as it does a count it sums itself. The
  `author` field of the same response is
  the repository owner, not the model's author: a re-upload names the
  uploader.
  Do: read the count and the owner from the call already made; call the
  owner what it is in provenance (`Method: repository_owner`). The owner is
  recorded as originator and as supplier (the repository is the distribution
  source).
- **A tensor element sum is not "trainable parameters".** It counts every
  stored tensor: `gpt2-tiny-decoder.onnx` 404256 holds a 262144-element
  uint8 causal mask (`transformer.h.0.attn.bias`, `[1, 1, 512, 512]`) and a
  32000-element transposed copy of `wte.weight`, so about 110112 are weights
  of their own; `marian-tiny-random` 174535 holds the 58101-element
  `final_logits_bias` buffer; `squeezenet1.1-7` 1235498 is 1235496 weights
  and a 2-element int64 reshape constant; the Hub's `gpt2` 137022720 (Hub
  API, 2026-10-15) holds attention-mask buffers on top of about 124.4M
  weights. Packed weights differ by format: GGUF shapes are logical (Q4_0
  `[64]` counts 64), GPTQ/AWQ/bitsandbytes Safetensors store packed integers
  (a GPTQ-style 64 x 64 layer: `qweight` I32 `[8, 64]` + `scales` + `qzeros` +
  `g_idx` = 648 against 4096), block-quantised ONNX under-counts, and a Hub
  total may cover one component of a repository only (an SDXL pipeline: the
  UNet).
  Do: call the value what it is (elements of stored tensors), say so in the
  SBOM, and never filter by dtype (int8 weights are parameters).
- **None of the five ONNX fixtures carries an author.** Their
  `metadata_props` are empty, as the PyThaiNLP files' were, so no end-to-end
  test could see `model_author` until a file with one was built with
  `onnx.helper`. The spec calls the value a comma-separated list, which a
  name such as `Doe, Jane` or `Foo, Inc.` breaks.
  Do: build a fixture with the field set, for every field a mapping reads
  (the same lesson as `domain` above), and write the comma caveat into the
  test.
