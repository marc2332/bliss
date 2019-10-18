#!/bin/bash
# Run flake8 linter on diff lines of stage area
git diff --cached -U0 | flake8 --diff
