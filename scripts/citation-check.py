#!/usr/bin/env python3
"""citation-check.py - Detect citation telephone game in text.

Inspired by Phineas Gage: Kotowicz (2007) found 60%+ of scientific
papers citing Gage include claims with no primary source basis.
Secondary sources citing secondary sources build myths.

Usage:
  python3 citation-check.py --file <path>    Check a file for citation patterns
  python3 citation-check.py --text "..."      Check inline text
  python3 citation-check.py --demo            Show Gage example
"""

import argparse
import re
import sys
from collections import Counter

# Hedging phrases that suggest secondhand citation
HEDGE_PATTERNS = [
    r'\b(?:is said to|reportedly|allegedly|is thought to|is believed to)\b',
    r'\b(?:according to (?:legend|myth|popular))',
    r'\b(?:famously|notoriously|well-known)\b',
    r'\b(?:it is (?:widely |commonly )?(?:known|accepted|believed))\b',
    r'\b(?:the (?:famous|well-known|classic) (?:case|example|story))\b',
]

# Citation format patterns
CITATION_PATTERNS = [
    r'\(([A-Z][a-z]+(?:\s+(?:et\s+al\.?|&\s+[A-Z][a-z]+))?,?\s*\d{4})\)',  # (Author, 2024)
    r'([A-Z][a-z]+(?:\s+(?:et\s+al\.?))?\s*\(\d{4}\))',  # Author (2024)
]

def analyze_text(text):
    """Analyze text for citation telephone patterns."""
    results = {
        'hedge_count': 0,
        'hedges': [],
        'citation_count': 0,
        'citations': [],
        'uncited_claims': 0,
        'sentences': 0,
        'risk_score': 0,
    }
    
    sentences = re.split(r'[.!?]+', text)
    results['sentences'] = len([s for s in sentences if s.strip()])
    
    # Find hedges
    for pattern in HEDGE_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            results['hedges'].append(match.group())
            results['hedge_count'] += 1
    
    # Find citations
    for pattern in CITATION_PATTERNS:
        for match in re.finditer(pattern, text):
            results['citations'].append(match.group(1) if match.lastindex else match.group())
            results['citation_count'] += 1
    
    # Count claim-like sentences without citations
    claim_words = r'\b(?:showed|proved|found|demonstrated|discovered|established|revealed)\b'
    for sent in sentences:
        if re.search(claim_words, sent, re.IGNORECASE):
            has_cite = any(re.search(p, sent) for p in CITATION_PATTERNS)
            if not has_cite:
                results['uncited_claims'] += 1
    
    # Risk score (0-10)
    score = 0
    if results['sentences'] > 0:
        hedge_ratio = results['hedge_count'] / results['sentences']
        score += min(4, int(hedge_ratio * 20))
    if results['citation_count'] == 0 and results['sentences'] > 3:
        score += 3
    score += min(3, results['uncited_claims'])
    results['risk_score'] = min(10, score)
    
    return results

def demo():
    """Show the Gage citation telephone in action."""
    print("=== Citation Telephone: Phineas Gage ===\n")
    
    examples = [
        ("PRIMARY (Harlow 1868)", 
         "The balance between his intellectual faculties and animal propensities seems to have been destroyed. He was fitful, irreverent, showing but little deference for his fellows."),
        ("SECONDARY (typical textbook)",
         "Gage famously became violent, aggressive, and sexually depraved after the accident. He reportedly drank heavily and was unable to hold any job. It is widely known that he spent his remaining years as a circus freak."),
        ("REALITY (Macmillan 2008)",
         "Gage drove stagecoaches in Chile for several years, a job requiring complex sensory-motor skills, social interaction in a foreign language, and rising at 4am for 13-hour routes. Harlow (1868) noted personality changes but no violence, drunkenness, or depravity."),
    ]
    
    for label, text in examples:
        print(f"--- {label} ---")
        r = analyze_text(text)
        risk = "🟢" if r['risk_score'] < 3 else "🟡" if r['risk_score'] < 6 else "🔴"
        print(f"  Risk: {risk} {r['risk_score']}/10")
        print(f"  Hedges: {r['hedge_count']} | Citations: {r['citation_count']} | Uncited claims: {r['uncited_claims']}")
        if r['hedges']:
            print(f"  Hedge phrases: {', '.join(r['hedges'])}")
        print()

def main():
    parser = argparse.ArgumentParser(description='Detect citation telephone patterns')
    parser.add_argument('--file', help='File to analyze')
    parser.add_argument('--text', help='Text to analyze')
    parser.add_argument('--demo', action='store_true', help='Show Gage example')
    args = parser.parse_args()
    
    if args.demo:
        demo()
    elif args.file:
        with open(args.file) as f:
            text = f.read()
        r = analyze_text(text)
        risk = "🟢" if r['risk_score'] < 3 else "🟡" if r['risk_score'] < 6 else "🔴"
        print(f"Risk: {risk} {r['risk_score']}/10 | Sentences: {r['sentences']} | Hedges: {r['hedge_count']} | Citations: {r['citation_count']} | Uncited claims: {r['uncited_claims']}")
        if r['hedges']:
            print(f"Hedge phrases: {', '.join(r['hedges'])}")
    elif args.text:
        r = analyze_text(args.text)
        risk = "🟢" if r['risk_score'] < 3 else "🟡" if r['risk_score'] < 6 else "🔴"
        print(f"Risk: {risk} {r['risk_score']}/10 | Hedges: {r['hedge_count']} | Citations: {r['citation_count']}")
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
