---
description: Generate (and optionally enrich) an SPDX 3 SBOM using Pitloom.
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Generate an SBOM with Pitloom

Follow the `pitloom-sbom` skill's Tier 1 procedure to generate an SPDX 3
SBOM for the current project. If an argument names a local model file or
a Hugging Face model ID, generate an AIBOM for that model instead (Tier
1's model mode). If the request (or an argument) asks to "enrich" the
result, additionally follow the skill's Tier 2 procedure afterwards.

$ARGUMENTS
