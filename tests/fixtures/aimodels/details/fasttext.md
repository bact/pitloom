---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# fastText fixtures

File details for `fasttext/`. See also: [AI model fixtures](../README.md)
(summary, licences, hostile files).

## fasttext/lid.176.ftz

| Property | Value |
| :--- | :--- |
| Format | fastText quantised (`ftz`) |
| Architecture | Supervised text classifier - 176-class language identification |
| Task | Language identification (176 languages) |
| Input | Text (UTF-8 string) |
| Output | Class probabilities `[176]` (one score per ISO language code) |
| Embedding dim | 16 |
| Labels | 176 ISO language codes (e.g. `__label__en`, `__label__de`, …) |
| Training | epoch=5, lr=0.05, wordNgrams=1, loss=hs |
| n-gram range | minn=2, maxn=4 |
| Size | 938 013 bytes (0.89 MB) |
| SHA-256 | `8f3472cfe8738a7b6099e8e999c3cbfae0dcd15696aac7d7738a8039db603e83` |
| License | CC-BY-SA-3.0 |
| Source | <https://fasttext.cc/docs/en/language-identification.html> (`lid.176.ftz`) |
| Required library | `fasttext` (`pip install pitloom[fasttext]`) |

Notable metadata extracted by the fastText extractor:

- `type_of_model` = `"supervised"` (from `args.model`)
- `hyperparameters`: `dim=16`, `lr=0.05`, `epoch=5`, `wordNgrams=1`,
  `minCount=1000`, `minn=2`, `maxn=4`, `neg=5`, `bucket=2000000`, `ws=5`
- `properties["lossName"]` = `"hs"` (hierarchical softmax)
- `properties["labels"]` contains 176 comma-separated language codes
- `name`, `description`, `version` are all `None`

---

## fasttext/sentimentdemo.bin

| Property | Value |
| :--- | :--- |
| Format | fastText binary (quantised, version 12) |
| Architecture | Supervised text classifier - 4-class Thai sentiment |
| Task | Sentiment classification: `pos`, `neg`, `neu`, `q` (question) |
| Input | Text (UTF-8 string, Thai language) |
| Output | Class probabilities `[4]` (`pos`, `neg`, `neu`, `q`) |
| Embedding dim | 21 |
| Labels | `__label__pos`, `__label__neg`, `__label__neu`, `__label__q` |
| Training | epoch=100, lr=0.05, wordNgrams=4, loss=softmax |
| n-gram range | minn=3, maxn=6 |
| Size | 96 339 bytes (0.09 MB) |
| SHA-256 | `a88bf0de7dff74d740cd45048521d319ff7c2560085f2604af265561e72ec4bc` |
| License | CC0-1.0 |
| Source | <https://github.com/bact/sentimentdemo> (`model.bin`) |
| Required library | `fasttext` (`pip install pitloom[fasttext]`) |

Notable metadata extracted by the fastText extractor:

- `type_of_model` = `"supervised"` (from `args.model`)
- `hyperparameters`: `dim=21`, `lr=0.05`, `epoch=100`, `wordNgrams=4`,
  `minCount=1`, `minn=3`, `maxn=6`, `neg=5`, `bucket=33502`, `ws=5`
- `properties["lossName"]` = `"softmax"`
- `properties["labels"]` = `"__label__pos,__label__neg,__label__neu,__label__q"`
- `name`, `description`, `version` are all `None` - fastText binary files
  do not embed a model name or description
