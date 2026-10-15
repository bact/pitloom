---
Created: 2026-10-15
Last-Modified: 2026-10-15
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# AI model scan limits: known limitations

See also: [AI model scan limits](ai-model-scan-limits.md) for the caps
themselves, the wheel gate and what a format cannot record, and
[AI model formats](ai-model-formats.md) for what each reader extracts.

The bounds keep a hostile file from being cheap to abuse; they do not make
it free. Figures are approximate, from measurements on one machine.

- **Memory and time of bounded input.** A pickle's decimal numbers are never
  converted, so a 1,000,000-digit number is refused in microseconds with the
  limit at its default or off (converting it with the limit off took 3.4 s on
  Python 3.10). The largest GGUF header accepted costs about 1.1 GB and 6
  seconds. A Safetensors header just under 16 MiB peaks near 0.8 GB. A pickle
  at the opcode cap costs about 100 MB and under a second in fickling. The
  `safetensors` library builds a model's whole `__metadata__` map, and the
  ONNX reader its whole result, before the entry cap trims them, so the cap
  bounds the SBOM, not one model's peak memory (about 0.6 GB for a 16 MiB
  `__metadata__`: 0.53 GB for one model, 0.58 GB for a wheel of 24 of them).
  The trimmed maps are rebuilt and the memory released, so a wheel's peak is
  its largest model's, not the sum of its models'.
- **Unbounded native parsers** (fastText, HDF5, ONNX). They are not
  bounded, only gated in wheels. With `--trust-wheel-model`, or in a
  project scan, a crafted file can use gigabytes (a 16 MiB ONNX measured
  about 3 GB; a 308-byte fastText header reached 5 GB and kept climbing)
  or crash or hang libhdf5.
- **No Ctrl-C while a native parser runs.** A signal handler does not run
  inside native code, so interrupting waits for the parser; kill the
  process if it hangs.
- **Disk.** A wheel scan copies each model it reads to a temporary
  directory, up to the budget (2 GiB by default), and removes it after.
- **Planned.** Header-only readers that never pass a file to a native
  library are planned for a future release. They would let the gated
  formats be read in wheels without `--trust-wheel-model` and replace
  several of the [caps](ai-model-scan-limits.md#size-and-count-caps).

## See also

- [AI model scan limits](ai-model-scan-limits.md) -- caps, gated formats
  in wheels, and what a format cannot record.
- [AI model formats](ai-model-formats.md) -- formats, extensions, install
  extras.
