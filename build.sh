#!/usr/bin/env bash
set -euo pipefail

python -m pip install -r requirements.txt

if ! command -v cargo >/dev/null 2>&1; then
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
    | sh -s -- -y --profile minimal --default-toolchain stable
  # shellcheck disable=SC1090
  source "$HOME/.cargo/env"
fi

cargo install \
  --git https://github.com/alphaiv-project/hmleq \
  --branch main \
  --package hmleq-cli \
  --bin hmleq \
  --root "$HOME/.cargo" \
  --force

hmleq_version=$("$HOME/.cargo/bin/hmleq" --version)
[[ "$hmleq_version" == "hmleq 0.2.0" ]] || {
  echo "Expected hmleq 0.2.0; found: $hmleq_version" >&2
  exit 1
}
touch .render-require-hmleq

