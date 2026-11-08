#!/usr/bin/env bash
set -euo pipefail

python -m pip install -r requirements.txt

# Render's build and runtime containers do not share the build user's home.
# Install the CLI inside the deploy artifact so the app can execute it at runtime.
export CARGO_HOME="$HOME/.cargo"
export PATH="$CARGO_HOME/bin:$PATH"

if ! command -v cargo >/dev/null 2>&1; then
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
    | sh -s -- -y --profile minimal --default-toolchain stable
  # shellcheck disable=SC1090
  source "$HOME/.cargo/env"
fi

cargo install \
  --git https://github.com/alphaiv-project/hmleq \
  --branch main \
  hmleq-cli \
  --bin hmleq \
  --root "$PWD/.render-tools" \
  --force

hmleq_version=$("$PWD/.render-tools/bin/hmleq" --version)
[[ "$hmleq_version" == "hmleq-cli 0.2.0" ]] || {
  echo "Expected hmleq-cli 0.2.0; found: $hmleq_version" >&2
  exit 1
}
touch .render-require-hmleq
