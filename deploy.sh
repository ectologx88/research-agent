#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
DIST_DIR="$PROJECT_ROOT/dist"

echo "=== Research Agent — Package & Deploy ==="

# 1. Clean
rm -rf "$DIST_DIR"
mkdir -p "$DIST_DIR/package"

# 2. Install deps into package dir
pip install \
  --target "$DIST_DIR/package" \
  --quiet \
  -r "$PROJECT_ROOT/requirements.txt"

# 3. Copy source
cp -r "$PROJECT_ROOT/src" "$DIST_DIR/package/src"

# 4. Zip
cd "$DIST_DIR/package"
zip -r9 "$DIST_DIR/lambda.zip" . -x '*.pyc' '__pycache__/*'

echo "Lambda package: $DIST_DIR/lambda.zip ($(du -h "$DIST_DIR/lambda.zip" | cut -f1))"

# 5. Deploy via Terraform
echo ""
echo "To deploy:"
echo "  cd $PROJECT_ROOT/terraform && terraform apply"
