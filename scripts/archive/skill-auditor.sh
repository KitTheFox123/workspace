#!/bin/bash
# skill-auditor.sh - Quick security audit for OpenClaw skills
# Inspired by Carapace Report + Shai-Hulud npm worm analysis
# Checks SKILL.md files for common malicious patterns

set -euo pipefail

SKILL_DIR="${1:-.}"
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m'

echo "🔍 Skill Auditor v1.0"
echo "Scanning: $SKILL_DIR"
echo "========================"

ALERTS=0
WARNINGS=0

check_pattern() {
    local file="$1" pattern="$2" severity="$3" desc="$4"
    if grep -qiE "$pattern" "$file" 2>/dev/null; then
        if [ "$severity" = "CRITICAL" ]; then
            echo -e "${RED}[CRITICAL]${NC} $desc"
            echo "  File: $file"
            echo "  Match: $(grep -iE "$pattern" "$file" | head -1 | sed 's/^[ \t]*//')"
            ((ALERTS++))
        else
            echo -e "${YELLOW}[WARNING]${NC} $desc"
            echo "  File: $file"
            ((WARNINGS++))
        fi
    fi
}

# Find all SKILL.md and shell scripts
find "$SKILL_DIR" -type f \( -name "SKILL.md" -o -name "*.sh" -o -name "*.js" \) | while read -r file; do
    echo -e "\n--- Checking: $file ---"
    
    # CRITICAL: Credential exfiltration
    check_pattern "$file" "curl.*-X.*POST.*(-d|--data).*(@|credentials|api_key|token)" "CRITICAL" \
        "POST request with credential data — possible exfiltration"
    
    check_pattern "$file" "curl.*\|.*bash" "CRITICAL" \
        "Remote script execution (curl | bash) — arbitrary code execution"
    
    check_pattern "$file" "\.openclaw/(openclaw|config)\.json" "CRITICAL" \
        "Accesses OpenClaw config — possible identity theft"
    
    check_pattern "$file" "webhook\.site|ngrok\.io|pipedream" "CRITICAL" \
        "Sends data to ephemeral webhook — likely exfiltration endpoint"
    
    check_pattern "$file" "\.npmrc|NPM_TOKEN|npm.*publish.*--force" "CRITICAL" \
        "NPM token access or forced publish — Shai-Hulud worm pattern"
    
    check_pattern "$file" "\.ssh/|id_rsa|id_ed25519" "CRITICAL" \
        "SSH key access — possible credential theft"
    
    check_pattern "$file" "\.aws/credentials|AWS_SECRET" "CRITICAL" \
        "AWS credential access"
    
    # WARNING: Suspicious but not necessarily malicious
    check_pattern "$file" "eval\s*\(" "WARNING" \
        "Uses eval() — potential code injection vector"
    
    check_pattern "$file" "child_process|exec\(|spawn\(" "WARNING" \
        "Spawns child processes — review what's being executed"
    
    check_pattern "$file" "postinstall|preinstall" "WARNING" \
        "Lifecycle hook — common malware injection point"
    
    check_pattern "$file" "base64.*decode|atob\(|Buffer\.from.*base64" "WARNING" \
        "Base64 decoding — may be obfuscating payload"
    
    check_pattern "$file" "process\.env" "WARNING" \
        "Reads environment variables — check which ones"
done

echo -e "\n========================"
echo -e "Results: ${RED}$ALERTS critical${NC}, ${YELLOW}$WARNINGS warnings${NC}"

if [ "$ALERTS" -gt 0 ]; then
    echo -e "${RED}⚠️  DO NOT INSTALL — critical security issues found${NC}"
    exit 1
elif [ "$WARNINGS" -gt 0 ]; then
    echo -e "${YELLOW}⚠️  Review warnings before installing${NC}"
    exit 0
else
    echo -e "${GREEN}✅ No suspicious patterns detected${NC}"
    exit 0
fi
