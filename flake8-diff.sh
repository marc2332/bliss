#!/bin/bash
# Run flake8 linter on diff lines of stage area
#   - never fails (always exit 0)
#     => errors are reported for information purpose only
git diff --cached -U0 | flake8 --diff --exit-zero
