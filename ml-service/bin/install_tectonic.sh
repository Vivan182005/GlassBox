#!/usr/bin/env bash
# Installs the Tectonic LaTeX engine (one self-contained binary, from the
# project's official GitHub releases) into ml-service/.tectonic and pre-fetches
# the TeX packages the resume templates use, so tailored resumes compile as
# PDFs in the candidate's own style.
#
# Render build command:
#   pip install -r requirements.txt && bash bin/install_tectonic.sh
set -euo pipefail
VERSION="0.15.0"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$HERE/.tectonic"
mkdir -p "$DEST/cache"
case "$(uname -s)-$(uname -m)" in
  Darwin-arm64)  TARGET="aarch64-apple-darwin" ;;
  Darwin-x86_64) TARGET="x86_64-apple-darwin" ;;
  Linux-x86_64)  TARGET="x86_64-unknown-linux-musl" ;;
  Linux-aarch64) TARGET="aarch64-unknown-linux-musl" ;;
  *) echo "No Tectonic build for $(uname -s)-$(uname -m); tailored resumes use Overleaf or the plain PDF." && exit 0 ;;
esac
if [ ! -x "$DEST/tectonic" ]; then
  URL="https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%40${VERSION}/tectonic-${VERSION}-${TARGET}.tar.gz"
  curl -fsSL "$URL" | tar -xz -C "$DEST"
fi
"$DEST/tectonic" --version
# Compile each template variant once so its packages are cached in the build.
TECTONIC_CACHE_DIR="$DEST/cache" python "$HERE/application/latex_warmup.py" || echo "Warm-up failed; packages download on first use."
