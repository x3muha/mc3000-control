#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(
  python3 -c \
    'import pathlib, re; text=pathlib.Path("mc3000_control/__init__.py").read_text(); print(re.search(r"__version__ = \"([^\"]+)\"", text).group(1))'
)"
ARCHIVE_NAME="mc3000-control-${VERSION}.tar.gz"

cd "${PROJECT_DIR}"
mkdir -p dist
git archive \
  --format=tar.gz \
  --prefix="mc3000-control-${VERSION}/" \
  --output="dist/${ARCHIVE_NAME}" \
  HEAD
(
  cd dist
  sha256sum "${ARCHIVE_NAME}" > "${ARCHIVE_NAME}.sha256"
)

echo "Created dist/${ARCHIVE_NAME}"
echo "Created dist/${ARCHIVE_NAME}.sha256"
