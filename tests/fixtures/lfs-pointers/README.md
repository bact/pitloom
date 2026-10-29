---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Git LFS pointer fixtures

See also: [`../../_lfs.py`](../../_lfs.py) (pointers built for a test, with
a real `oid` and `size`);
[`../../core/test_lfs_pointer.py`](../../core/test_lfs_pointer.py) (the
grammar tests that read these).

Real Git LFS pointers, byte for byte as the Hugging Face Hub serves them
from `https://huggingface.co/<id>/raw/main/<path>`, fetched 2026-10-29.
Only the pointer text (three LF-terminated lines, under 140 bytes) is
committed, never the content it stands in for. `.gitattributes` marks them
`-text`, so a Windows checkout keeps the LF line ends.

| File | Repository `<id>` | `<path>` | Licence | LFS size (bytes) |
| --- | --- | --- | --- | --- |
| `aa-lcr-extracted-text.zip` | `datasets/ArtificialAnalysis/AA-LCR` | `extracted_text/AA-LCR_extracted-text.zip` | Apache-2.0 | 4023468 |
| `aime-2024-problems.parquet` | `datasets/Maxwell-Jia/AIME_2024` | `aime_2024_problems.parquet` | MIT | 37189 |
| `bert-tiny-pytorch-model.bin` | `prajjwal1/bert-tiny` | `pytorch_model.bin` | MIT | 17756393 |
| `humaneval-test.parquet` | `datasets/openai/openai_humaneval` | `openai_humaneval/test-00000-of-00001.parquet` | MIT | 83920 |
| `static-js-app-main.js` | `spaces/whitphx/static-js-app-lfs-sample` | `main.js` | MIT | 28 |

They cover a dataset, a model next to ordinary files, a nested non-model
archive and a Space. No real pointer of the earlier spec URLs or with CRLF
line ends was found; `tests/_lfs.py` builds those.
