#!/usr/bin/env bash
set -euo pipefail

# Render's native build filesystem is not writable under /var/lib/apt.
# Extract a newer FreeType into the deploy artifact instead of using apt.
case "$(uname -m)" in
  x86_64)
    FREETYPE_DEB_URL="https://deb.debian.org/debian/pool/main/f/freetype/libfreetype6_2.12.1+dfsg-5+deb12u4_amd64.deb"
    ;;
  *)
    echo "ERROR: bundled FreeType package is currently configured for x86_64 only." >&2
    exit 1
    ;;
esac

mkdir -p .render-libs
curl --fail --location --retry 3 "$FREETYPE_DEB_URL" -o /tmp/libfreetype6.deb
dpkg-deb -x /tmp/libfreetype6.deb .render-libs
FREETYPE_LIB="$(find "$PWD/.render-libs" -type f -name 'libfreetype.so.6.*' | head -n 1)"
if [[ -z "$FREETYPE_LIB" ]]; then
  echo "ERROR: extracted FreeType shared library was not found." >&2
  exit 1
fi
echo "Bundled FreeType: $FREETYPE_LIB"

python -m pip install -r requirements.txt

# Preload the bundled library before importing rhwp so its native extension
# resolves libfreetype.so.6 from the deploy artifact, not the host image.
python - <<'PY'
import ctypes
import pathlib
import subprocess
import sys

root = pathlib.Path(".render-libs")
candidates = list(root.rglob("libfreetype.so.6"))
if not candidates:
    raise RuntimeError("Bundled libfreetype.so.6 symlink was not found")
ctypes.CDLL(str(candidates[0]), mode=ctypes.RTLD_GLOBAL)

try:
    import rhwp
except Exception as exc:
    print(f"ERROR: rhwp-python import failed during build: {exc}", file=sys.stderr)
    import importlib.util
    spec = importlib.util.find_spec("rhwp")
    if spec and spec.submodule_search_locations:
        package_dir = pathlib.Path(next(iter(spec.submodule_search_locations)))
        for native_module in package_dir.glob("*.so"):
            print(f"===== ldd {native_module} =====")
            subprocess.run(["ldd", str(native_module)], check=False)
    raise

print(f"rhwp-python import OK: {getattr(rhwp, '__file__', 'unknown path')}")

import hmleqx
smoke_result = hmleqx.to_latex("1 over 2")
if not isinstance(smoke_result, str) or not smoke_result.strip():
    raise RuntimeError("hmleqx smoke test returned an empty result")
print(f"hmleqx import and conversion OK: {hmleqx.version()}")
PY

