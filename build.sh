#!/usr/bin/env bash
set -euo pipefail

# rhwp-python's native extension requires FreeType symbols that may be missing
# from the base Render image. Install the system runtime before Python packages.
if command -v apt-get >/dev/null 2>&1; then
  apt-get update
  apt-get install -y --no-install-recommends libfreetype6
  rm -rf /var/lib/apt/lists/*
else
  echo "ERROR: apt-get is unavailable; cannot provision libfreetype6." >&2
  exit 1
fi

echo "===== FreeType runtime ====="
if command -v freetype-config >/dev/null 2>&1; then
  freetype-config --version
fi
if command -v ldconfig >/dev/null 2>&1; then
  ldconfig -p | grep -i freetype || true
fi

python -m pip install -r requirements.txt

# Fail during build, rather than on every user upload, if rhwp's native
# extension cannot resolve its runtime dependencies in the Render image.
python - <<'PY'
import importlib.util
import pathlib
import subprocess
import sys

try:
    import rhwp
except Exception as exc:
    print(f"ERROR: rhwp-python import failed during build: {exc}", file=sys.stderr)
    spec = importlib.util.find_spec("rhwp")
    if spec and spec.submodule_search_locations:
        package_dir = pathlib.Path(next(iter(spec.submodule_search_locations)))
        for native_module in package_dir.glob("*.so"):
            print(f"===== ldd {native_module} =====")
            subprocess.run(["ldd", str(native_module)], check=False)
    raise

print(f"rhwp-python import OK: {getattr(rhwp, '__file__', 'unknown path')}")
PY

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
