#!/usr/bin/env bash
# Optional bootstrap script for VS Code Server instances (see vscode-server-template.yaml).
# Runs automatically when deployed assets include this file at /Workshop/bootstrap.sh.
set -euo pipefail

WORKSHOP_DIR="${HOME:-/home/ec2-user}/Workshop"
SRC_DIR="${WORKSHOP_DIR}/src"

echo "=== Secure Serverless workshop bootstrap ==="
echo "Workshop directory: ${WORKSHOP_DIR}"

if [[ ! -d "${SRC_DIR}" ]]; then
  echo "Expected ${SRC_DIR} — unzip workshop assets into ${WORKSHOP_DIR} first."
  exit 1
fi

python3 --version
sam --version
psql --version

echo ""
echo "Next steps:"
echo "  1. Configure Aurora IAM auth and apply schema (see README.md)"
echo "  2. cd ${SRC_DIR} && sam build && sam deploy"
echo "  3. Test: curl -s \"\${API_URL}/socks\" | jq ."
