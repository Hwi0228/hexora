#!/usr/bin/env bash
set -euo pipefail

python -m pip install -r requirements-dev.txt
pip-compile --resolver=backtracking --strip-extras --no-annotate \
  --output-file requirements.lock requirements.in
