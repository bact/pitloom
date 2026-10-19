---
Created: 2026-10-18
Last-Modified: 2026-10-18
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# SBOM minimum elements: question bank

See also: [`minimum-elements.md`](minimum-elements.md) (the checklists and field
mappings), [`minimum-elements-workflow.md`](minimum-elements-workflow.md).

## Question bank (educated guesses for hard-to-derive elements)

Use these as a starting point for the "where might this information be" prompt
the skill gives the user for elements it can't resolve itself -- adapt to what's
actually in the project.

- **SBOM Author** (when `[[tool.pitloom.creator]]` isn't set): "Pitloom's own
  `CreationInfo` currently only names Pitloom itself as the generating tool, not
  the person or organisation that ran it. Who should be recorded as the SBOM
  author -- you, or an organisation? This can also be set permanently via
  `[[tool.pitloom.creator]]` in `pyproject.toml` (note the double brackets --
  it's an array of tables) so future runs don't need to ask -- and it also
  records the main package's supplier (`suppliedBy`) at the same time."
- **Component/Model Producer**: for a model, first look at the `ai_AIPackage`'s
  `originatedBy`: a generic `Agent` there already answers it (from the file's
  author field or the Hub repository owner), and the only open question is
  whether it is a person or an organisation, which the model card usually
  says (a fragment adds the `Person`/`Organization` beside the `Agent`). If
  it is absent, or only the owner of a re-upload: "Is this dependency/model
  something your organisation built, or a third-party component? If
  third-party, do you know the maintaining organisation or project (check
  the package's PyPI page, GitHub org, or model card)?" Non-interactive: add
  a typed agent only when the local model card states it (`Role: declared`
  or `inferred`), else report the generic `Agent` as the producer and
  person-versus-organisation as open.
- **Model parameter count** (no `parameters` entry): "Does the model card
  or paper state the parameter count?" Read the local card first. The value
  is a decimal integer, as Pitloom writes it; a rounded label (`7B`) is not
  one, so leave the entry out and quote the label in the report.
  Non-interactive: use a local card only, else report the gap.
- **BSI creator contact** (DOC-001, COMP-001): "BSI wants the SBOM's creator,
  and each component's creator, as a person or organisation with an e-mail
  address. Who, and which address?" The SBOM creator goes in
  `[[tool.pitloom.creator]]` (`name`, `type`, `email`) or `--creator-name`,
  `--creator-type`, `--creator-email`; the main package's creator comes from an
  e-mail in `[project].authors`. Non-interactive: use what the project already
  declares, else report the gap; never invent an address.
- **BSI distribution artifact** (COMP-004, COMP-007): "Which built file is
  distributed (e.g. `dist/<name>-<version>-py3-none-any.whl`)?" Its SHA-512 is
  computed from that file (`sha512sum`, or `shasum -a 512` on macOS) only
  after the user names it; the SBOM then describes that archive, so regenerate
  when it is rebuilt. Non-interactive: leave the hash out and report it.
- **BSI structured property and dependency completeness** (COMP-010,
  COMP-005): "Is this component structured (a container such as a wheel or
  archive) or unstructured firmware?" and "Is the dependency list complete?"
  Both are the user's claims. Non-interactive: leave them out and report them.
- **security.txt** (BSI COMP-017, optional): "Does the project publish a
  security policy or `security.txt` URL?" Non-interactive: leave it out; it is
  optional.
- **SBOM Author Signature**: "This requires a detached digital signature over
  the SBOM using your organisation's own signing infrastructure (see NIST SP
  800-57 Pt. 1 for key-management guidance). Pitloom doesn't generate signatures
  -- do you already have a signing process, or is this out of scope for now?"
- **Model license**: "Does the model have its own licence, separate from the
  project's? Check the model card / a `LICENSE` file next to the model weights,
  or the hub page if it came from Hugging Face."
- **Dataset provenance**: "Where did this dataset come from -- collected
  in-house, downloaded from a public source, or derived from another dataset in
  this project? Check the dataset's own README/data card, or a
  data-collection/labelling pipeline doc if one exists."
- **Dataset sensitivity**: "Does this dataset contain personal data (PII),
  copyrighted material, or other sensitive content (financial, medical, national
  security)? This generally can't be inferred from the data alone -- best
  answered by whoever curated it."
- **Model training properties**: "What training approach was used --
  pre-training from scratch, fine-tuning an existing model, RLHF, or something
  else? A model card's 'Training' or 'Methodology' section usually states this
  if one exists."
