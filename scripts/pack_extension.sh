#!/usr/bin/env bash
# Zips extension/ into the site's public folder, so "download it" in the
# Apply drawer serves the current version. Runs before every frontend build.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/frontend/public/glassbox-autofill.zip"
rm -f "$OUT"
cd "$ROOT/extension" && zip -qr "$OUT" . -x '.*' && echo "Packed $OUT"
