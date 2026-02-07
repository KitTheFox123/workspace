#!/bin/bash
# consensus-checker.sh — Detect potential collective illusions in discussions
# Inspired by Todd Rose's "Collective Illusions" (2022)
# 
# Analyzes comment threads to detect signs of:
# 1. Cascade copying (everyone agreeing with no independent reasoning)
# 2. Self-silencing (few comments relative to views)
# 3. Loud-fringe amplification (small group dominating conversation)
#
# Usage: ./consensus-checker.sh <mode> [args]
#   analyze <file>    — Analyze a discussion thread (one comment per line)
#   signals           — Print warning signs of collective illusions
#   test              — Run with sample data

set -euo pipefail

signals() {
    cat <<'EOF'
🔍 WARNING SIGNS OF COLLECTIVE ILLUSIONS (Rose, 2022):

1. CASCADE COPYING
   - Everyone agrees but nobody gives independent reasons
   - "+1" and "this" dominate the replies
   - Ask: "If the first comment disagreed, would the thread look different?"

2. SELF-SILENCING
   - High view count, low comment count
   - Comments are generic/safe ("great post!")
   - No substantive disagreement anywhere in thread

3. LOUD-FRINGE AMPLIFICATION
   - 2-3 voices produce 80% of content (Twitter: 10% make 80%)
   - Extreme positions repeated frequently
   - Moderate/nuanced takes get no engagement

4. PREFERENCE FALSIFICATION (Timur Kuran)
   - People publicly state opposite of private belief
   - Visible in: corporate meetings, social media, voting behavior
   - Test: anonymous polls vs public hand-raises diverge

💡 ANTIDOTES:
   - Ask "why do you believe that?" before copying
   - Inject uncertainty: "I'm not sure, on one hand... on the other..."
   - Anonymous polling before public discussion
   - Track: do stated preferences match actual behavior?

📊 KEY STAT: 2/3 of Americans admit to self-silencing (Cato/Populace)
   - Primary reason: not wanting to hurt feelings (not cancel culture)
   - Most people believe others are "too sensitive" — but privately
     report they themselves want to hear differing views
EOF
}

analyze() {
    local file="$1"
    if [[ ! -f "$file" ]]; then
        echo "Error: File not found: $file"
        exit 1
    fi

    local total_comments=$(wc -l < "$file")
    local agreement_words=$(grep -ic '\b\(agree\|exactly\|this\|yes\|\+1\|same\|right\|true\)\b' "$file" || echo 0)
    local disagreement_words=$(grep -ic '\b\(disagree\|but\|however\|actually\|wrong\|no\|pushback\|counterpoint\)\b' "$file" || echo 0)
    local unique_authors=$(awk -F: '{print $1}' "$file" | sort -u | wc -l)
    
    echo "📊 CONSENSUS ANALYSIS"
    echo "===================="
    echo "Total comments: $total_comments"
    echo "Unique voices: $unique_authors"
    echo "Agreement signals: $agreement_words"
    echo "Disagreement signals: $disagreement_words"
    echo ""
    
    if (( total_comments > 0 )); then
        local agreement_ratio=$(echo "scale=2; $agreement_words / $total_comments" | bc)
        local voice_ratio=$(echo "scale=2; $unique_authors / $total_comments" | bc)
        
        echo "Agreement ratio: $agreement_ratio (>0.7 = potential cascade)"
        echo "Voice diversity: $voice_ratio (< 0.3 = loud-fringe risk)"
        echo ""
        
        # Warnings
        if (( $(echo "$agreement_ratio > 0.7" | bc -l) )); then
            echo "⚠️  HIGH AGREEMENT — possible cascade copying"
            echo "   Ask: Are people agreeing independently or copying?"
        fi
        
        if (( $(echo "$voice_ratio < 0.3" | bc -l) )); then
            echo "⚠️  LOW VOICE DIVERSITY — few people dominating"
            echo "   10% of Twitter users create 80% of content (Pew Research)"
        fi
        
        if (( disagreement_words == 0 && total_comments > 5 )); then
            echo "⚠️  ZERO DISAGREEMENT in 5+ comments — self-silencing likely"
            echo "   2/3 of people self-silence (Populace/Cato research)"
        fi
    fi
}

test_mode() {
    local tmpfile=$(mktemp)
    cat > "$tmpfile" <<'EOF'
alice: Great idea, totally agree!
bob: This is exactly what we need
charlie: +1, couldn't agree more
alice: Yes, and building on that...
dave: Same here, this resonates
eve: Absolutely right
alice: Glad everyone's on the same page
bob: Exactly, this is the way forward
EOF
    echo "📝 Test data (8 comments, heavy agreement):"
    echo "---"
    cat "$tmpfile"
    echo "---"
    echo ""
    analyze "$tmpfile"
    rm "$tmpfile"
}

case "${1:-signals}" in
    analyze)  analyze "${2:?Usage: consensus-checker.sh analyze <file>}" ;;
    signals)  signals ;;
    test)     test_mode ;;
    *)        echo "Usage: $0 {analyze|signals|test}" ;;
esac
