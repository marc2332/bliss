#!/bin/bash
# This script installs a pre-commit hook on the local repository
# It allows black to run before any git commit.

# Install pre-commit, with a local install fallback
pip install --quiet --upgrade pre-commit 2>/dev/null \
    || pip install --quiet --user --upgrade pre-commit

# Install the pre-commit hook on the local repository
pre-commit install
