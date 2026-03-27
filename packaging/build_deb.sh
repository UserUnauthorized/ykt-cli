#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 3 ]]; then
    echo "Usage: $0 <standalone-dir> <platform> <version>"
    echo "Example: $0 dist/ykt-cli-linux-amd64 linux-amd64 1.0.0"
    exit 1
fi

STANDALONE_DIR="$1"
PLATFORM="$2"
VERSION="$3"

# Map platform to dpkg architecture
case "$PLATFORM" in
    linux-amd64) ARCH="amd64" ;;
    linux-arm64) ARCH="arm64" ;;
    *)
        echo "Error: unsupported platform '$PLATFORM' (expected linux-amd64 or linux-arm64)"
        exit 1
        ;;
esac

if [[ ! -d "$STANDALONE_DIR" ]]; then
    echo "Error: standalone directory '$STANDALONE_DIR' does not exist"
    exit 1
fi

OUTPUT_NAME="ykt-cli-${PLATFORM}"
STAGING="/tmp/ykt-cli_${VERSION}_${ARCH}"
INSTALL_DIR="${STAGING}/usr/local/lib/ykt-cli"
BIN_DIR="${STAGING}/usr/local/bin"

# Clean previous build
rm -rf "$STAGING"

# Create directory structure
mkdir -p "$INSTALL_DIR"
mkdir -p "$BIN_DIR"
mkdir -p "${STAGING}/DEBIAN"

# Write control file
cat > "${STAGING}/DEBIAN/control" <<EOF
Package: ykt-cli
Version: ${VERSION}
Architecture: ${ARCH}
Maintainer: UserUnauthorized <noreply@401.moe>
Description: CLI tool for YuKeTang (Rain Classroom) platform
 Automates course video watching and slide downloading.
EOF

# Copy standalone build
cp -a "$STANDALONE_DIR"/. "$INSTALL_DIR/"

# Create symlink
ln -sf /usr/local/lib/ykt-cli/ykt "$BIN_DIR/ykt"

# Build .deb package
mkdir -p dist
dpkg-deb --root-owner-group --build "$STAGING" "dist/${OUTPUT_NAME}.deb"

echo "Built dist/${OUTPUT_NAME}.deb"
