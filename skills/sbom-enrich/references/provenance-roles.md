---
Created: 2026-10-29
Last-Modified: 2026-10-29
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Provenance markers and roles

See also: `../SKILL.md` ("Contribute enrichment as a fragment", steps 4 and 6,
which hold the rules), `examples.md` (complete fragments) and
`minimum-elements-questions.md` (step d's question bank).

Every inferred field's `comment` (or the fragment's `CreationInfo.comment`)
carries one provenance marker. Include your own agent name, vendor and today's
date when you know them: Pitloom cannot verify them, but they help a reviewer.

```text
Source: <your agent name> (<vendor>) | Role: inferred | Date: <ISO 8601 date>
```

Fill in your own identity, e.g. `Source: Claude Code (Anthropic) | Role:
inferred | Date: 2026-08-10` or `Source: Codex (OpenAI) | Role: inferred |
Date: 2026-08-10`. Never copy another agent's name. If you don't know your
own name or vendor, fall back to the generic form rather than guessing:

```text
Source: AI agent | Role: inferred
```

**In an interactive session** (a human present to answer), a field the SBOM
author directly tells you is not an inference: mark it `sbomAuthorSupplied`,
not `inferred`:

```text
Source: SBOM author | Role: sbomAuthorSupplied | Date: <ISO 8601 date>
```

## The `Role:` vocabulary an agent uses

- `inferred` -- your own reasoning from prose.
- `declared` -- the subject's own claim, read where it states it (a file's own
  licence field).
- `externalReported` -- another party's determination, relayed as given (a
  paper's, a hub's).
- `sbomAuthorSupplied` -- the SBOM author stated the fact themselves.

## Step 4: the answer decides the role

Is the answer the fact, or a pointer to the fact?

- The SBOM author states the fact itself ("it's MIT", "yes, trained on our
  internal support-ticket corpus"): mark it `Source: SBOM author | Role:
  sbomAuthorSupplied | Date: <ISO 8601 date>`, never `Role: inferred`; you
  didn't derive it, you relayed what you were told.
- The SBOM author points at a source instead ("look at CONTRIBUTING.md", "read
  the wiki page", "try the HF card", "infer it from the changelog"): go look.
  The role is *never* `sbomAuthorSupplied` here. It is whichever of
  `declared`/`externalReported`/`inferred` matches how you actually got the
  value from that source once you looked.
- Using a source outside the project needs the consent of step 5 first. That
  gate is not a role: it never makes the result `sbomAuthorSupplied`.

## Step 6: overriding the deterministic result

The deterministic result wins by default: if step 2 already set a field, do
not re-propose a different value in your own fragment (two conflicting
relationships on one subject, no way to tell which is current). Override only
when prose clearly contradicts it (e.g. a stale frontmatter `license:`): record
*both* values and your reasoning in that entry's provenance comment,

```text
Source: <your agent name> (<vendor>) | Role: inferred | Overrides: <deterministic value> | Reason: <why>
```

and say so in your final report (step 11) -- never silently. A complete
override example is in `examples.md`.

## Paths in fragments

Write any file path in a field or comment POSIX-style (`docs/model-card.md`,
not `docs\model-card.md`) on every OS: Pitloom-generated SBOMs are
byte-identical across operating systems, and a backslash path would be the one
thing that isn't.

## Ids in a fragment

A `Relationship` must point at real ids: copy the model's `ai_AIPackage`
`spdxId` from the base SBOM as its `from`, and give every new element its own
`spdxId`. To add to a base element's own properties (`originatedBy`, an
`ai_hyperparameter` entry), restate it with the base's `spdxId` and `name`
exactly: a stale id adds a second `ai_AIPackage`, silently, and it still
validates; lists merge as a union, a base value wins.
