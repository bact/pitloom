# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Core SPDX models and data structures.

Import a name from its own module (``pitloom.core.provenance``), not from
here: an eager import in this file runs whenever any ``pitloom.core`` module
loads, and ``pitloom.messages`` reaches ``pitloom.core`` while it loads.
"""
