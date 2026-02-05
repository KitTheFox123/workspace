#!/bin/bash
# credential-scanner.sh - Scan for potential credential leaks before publishing
# Run this BEFORE any git push to public repos

set -e

RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

WORKSPACE="${1:-.}"
ISSUES_FOUND=0

echo "🔍 Scanning $WORKSPACE for potential credential leaks..."
echo ""

# Patterns to search for
PATTERNS=(
    # API keys and tokens
    'api[_-]?key["\s:=]+["\047]?[A-Za-z0-9_-]{20,}'
    'api[_-]?token["\s:=]+["\047]?[A-Za-z0-9_-]{20,}'
    'bearer["\s:]+[A-Za-z0-9_-]{20,}'
    'authorization["\s:]+[A-Za-z0-9_-]{20,}'
    
    # Specific services
    'sk-[A-Za-z0-9]{32,}'          # OpenAI
    'ghp_[A-Za-z0-9]{36}'          # GitHub PAT
    'gho_[A-Za-z0-9]{36}'          # GitHub OAuth
    'github_pat_[A-Za-z0-9_]{22,}' # GitHub fine-grained PAT
    'xox[baprs]-[A-Za-z0-9-]{10,}' # Slack
    'sk_live_[A-Za-z0-9]{24,}'     # Stripe
    
    # Generic secrets
    'password["\s:=]+["\047][^"\047]{8,}'
    'secret[_-]?key["\s:=]+["\047]?[A-Za-z0-9_-]{16,}'
    'private[_-]?key["\s:=]+'
    
    # AWS
    'AKIA[0-9A-Z]{16}'
    'aws[_-]?secret[_-]?access[_-]?key'
    
    # Base64 encoded secrets (common pattern)
    'eyJ[A-Za-z0-9_-]*\.eyJ[A-Za-z0-9_-]*'  # JWT tokens
)

# Files to always exclude from scan
EXCLUDE_PATTERNS=(
    "*.git/*"
    "credential-scanner.sh"  # This file itself
)

# Build exclude args for grep
EXCLUDE_ARGS=""
for pattern in "${EXCLUDE_PATTERNS[@]}"; do
    EXCLUDE_ARGS="$EXCLUDE_ARGS --exclude=$pattern"
done

echo "Checking for sensitive patterns..."
echo "=================================="

for pattern in "${PATTERNS[@]}"; do
    # Use grep with extended regex, case insensitive
    matches=$(grep -rliE "$pattern" "$WORKSPACE" $EXCLUDE_ARGS 2>/dev/null || true)
    if [ -n "$matches" ]; then
        echo -e "${RED}⚠️  Potential match for pattern: $pattern${NC}"
        echo "$matches" | while read -r file; do
            echo -e "   ${YELLOW}→ $file${NC}"
            # Show context (but mask potential secrets)
            grep -niE "$pattern" "$file" 2>/dev/null | head -3 | sed 's/\(.\{60\}\).*/\1.../' | while read -r line; do
                echo "      $line"
            done
        done
        echo ""
        ISSUES_FOUND=$((ISSUES_FOUND + 1))
    fi
done

# Check for common credential file names
echo ""
echo "Checking for credential file names..."
echo "======================================"

CRED_FILES=(
    "credentials.json"
    "secrets.json"
    "config.json"
    ".env"
    "*.pem"
    "*.key"
    "id_rsa"
    "id_ed25519"
)

for pattern in "${CRED_FILES[@]}"; do
    matches=$(find "$WORKSPACE" -name "$pattern" -type f 2>/dev/null || true)
    if [ -n "$matches" ]; then
        echo -e "${RED}⚠️  Found credential-like file: $pattern${NC}"
        echo "$matches" | while read -r file; do
            echo -e "   ${YELLOW}→ $file${NC}"
        done
        ISSUES_FOUND=$((ISSUES_FOUND + 1))
    fi
done

# Check .gitignore exists and has key exclusions
echo ""
echo "Checking .gitignore..."
echo "======================"

if [ -f "$WORKSPACE/.gitignore" ]; then
    echo -e "${GREEN}✓ .gitignore exists${NC}"
    
    REQUIRED_IGNORES=("credentials" "secrets" "*.key" "*.pem" ".env")
    for ignore in "${REQUIRED_IGNORES[@]}"; do
        if grep -q "$ignore" "$WORKSPACE/.gitignore" 2>/dev/null; then
            echo -e "  ${GREEN}✓ Ignoring: $ignore${NC}"
        else
            echo -e "  ${YELLOW}⚠ Consider adding: $ignore${NC}"
        fi
    done
else
    echo -e "${RED}⚠️  No .gitignore found! Create one before publishing.${NC}"
    ISSUES_FOUND=$((ISSUES_FOUND + 1))
fi

# Summary
echo ""
echo "=================================="
if [ $ISSUES_FOUND -eq 0 ]; then
    echo -e "${GREEN}✅ No obvious credential leaks detected${NC}"
    echo "   (Manual review still recommended before publishing)"
    exit 0
else
    echo -e "${RED}❌ Found $ISSUES_FOUND potential issues${NC}"
    echo "   Review and fix before publishing!"
    exit 1
fi
