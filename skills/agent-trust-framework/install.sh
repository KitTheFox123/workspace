#!/bin/bash
# Install Agent Trust Framework skill
# Copies trust tools from scripts/ to skill directory

SKILL_DIR="$(dirname "$0")"
SCRIPTS_DIR="${SKILL_DIR}/../../scripts"

TOOLS=(
  trust-axis-scorer.py
  soul-hash-canonicalizer.py
  replay-guard.py
  attestation-density-scorer.py
  behavioral-trajectory-scorer.py
  ba-sidecar-composer.py
  failure-taxonomy-detector.py
  benford-attestation-detector.py
)

echo "Installing Agent Trust Framework..."
for tool in "${TOOLS[@]}"; do
  if [ -f "${SCRIPTS_DIR}/${tool}" ]; then
    cp "${SCRIPTS_DIR}/${tool}" "${SKILL_DIR}/"
    echo "  ✅ ${tool}"
  else
    echo "  ⚠️  ${tool} not found in scripts/"
  fi
done

echo ""
echo "Done. Run any tool with: python3 ${SKILL_DIR}/<tool>"
echo "See SKILL.md for documentation."
