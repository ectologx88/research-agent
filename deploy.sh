#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
DIST_DIR="$PROJECT_ROOT/dist"

echo "=== Research Agent — Package & Deploy ==="

# 1. Clean
rm -rf "$DIST_DIR"
mkdir -p "$DIST_DIR/package"

# 2. Install deps into package dir
# pydantic-core has a native C extension; use a manylinux wheel so it runs on
# Lambda's Amazon Linux 2023 (glibc 2.34) regardless of the local glibc version.
pip install \
  --target "$DIST_DIR/package" \
  --platform manylinux2014_x86_64 \
  --implementation cp \
  --python-version 3.12 \
  --only-binary=:all: \
  --quiet \
  pydantic pydantic-core pydantic-settings

# Install remaining pure-Python deps normally
pip install \
  --target "$DIST_DIR/package" \
  --quiet \
  boto3 requests tenacity pyzotero

# 3. Copy source
cp -r "$PROJECT_ROOT/src" "$DIST_DIR/package/src"
cp -r "$PROJECT_ROOT/config" "$DIST_DIR/package/config"
cp -r "$PROJECT_ROOT/shared" "$DIST_DIR/package/shared"

# 4. Zip
cd "$DIST_DIR/package"
zip -r9 "$DIST_DIR/lambda.zip" . -x '*.pyc' '__pycache__/*'

echo "Lambda package: $DIST_DIR/lambda.zip ($(du -h "$DIST_DIR/lambda.zip" | cut -f1))"

# 5. Deploy via Terraform
echo ""
echo "To deploy:"
echo "  cd $PROJECT_ROOT/terraform && terraform apply"
