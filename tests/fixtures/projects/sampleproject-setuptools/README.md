# sampleproject-setuptools

A minimal sample project used as a fixture for testing Pitloom's setuptools
metadata extraction support.

This project demonstrates the common transitional pattern where:

- `pyproject.toml` contains only the `[build-system]` table (setuptools backend)
- `setup.cfg` contains all project metadata (`[metadata]` and `[options]`)
- `setup.py` is a minimal shim that delegates to `setup.cfg`
