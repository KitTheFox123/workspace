#!/usr/bin/env python3
"""
imagination-inflation-detector.py

Detects scope drift via the imagination inflation mechanism:
repeated exposure to stale scope inflates confidence it's still valid.

Measures semantic distance between current actions and original scope,
flags when an agent's behavior drifts without scope renewal.

Based on Garry et al. 1996 (imagination inflation) and
Gollwitzer 1999 (implementation intentions).

Usage:
    python imagination-inflation-detector.py --scope HEARTBEAT.md --log memory/2026-03-07.md
    python imagination-inflation-detector.py --demo
"""

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def extract_scope_terms(text: str) -> Counter:
    """Extract meaningful terms from scope document."""
    stop = {'the','a','an','is','are','was','were','be','been','being',
            'have','has','had','do','does','did','will','would','shall',
            'should','may','might','can','could','and','but','or','nor',
            'for','yet','so','in','on','at','to','from','by','with',
            'of','that','this','it','its','if','then','else','when',
            'not','no','yes','all','each','every','any','some','most'}
    words = re.findall(r'[a-z]{3,}', text.lower())
    return Counter(w for w in words if w not in stop)


def jaccard_similarity(a: Counter, b: Counter) -> float:
    """Jaccard similarity between two term sets."""
    a_set = set(a.keys())
    b_set = set(b.keys())
    if not a_set and not b_set:
        return 1.0
    intersection = a_set & b_set
    union = a_set | b_set
    return len(intersection) / len(union)


def cosine_similarity(a: Counter, b: Counter) -> float:
    """Cosine similarity between two term frequency vectors."""
    all_terms = set(a.keys()) | set(b.keys())
    if not all_terms:
        return 1.0
    dot = sum(a.get(t, 0) * b.get(t, 0) for t in all_terms)
    mag_a = sum(v**2 for v in a.values()) ** 0.5
    mag_b = sum(v**2 for v in b.values()) ** 0.5
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def extract_sections(log_text: str) -> list[dict]:
    """Extract timestamped sections from a daily log."""
    sections = []
    pattern = r'##\s+(\d{1,2}:\d{2})\s+UTC\s*[-—]?\s*(.*?)(?=\n##\s+\d{1,2}:\d{2}|$)'
    for m in re.finditer(pattern, log_text, re.DOTALL):
        time_str = m.group(1)
        content = m.group(2).strip()
        sections.append({
            'time': time_str,
            'content': content,
            'terms': extract_scope_terms(content),
            'length': len(content),
        })
    return sections


def detect_drift(scope_terms: Counter, sections: list[dict]) -> list[dict]:
    """Detect drift: sections diverging from scope."""
    results = []
    for i, section in enumerate(sections):
        j_sim = jaccard_similarity(scope_terms, section['terms'])
        c_sim = cosine_similarity(scope_terms, section['terms'])
        
        # Combined drift score (0 = perfectly aligned, 1 = fully drifted)
        drift = 1.0 - (0.4 * j_sim + 0.6 * c_sim)
        
        # Novel terms not in scope
        novel = set(section['terms'].keys()) - set(scope_terms.keys())
        top_novel = sorted(novel, key=lambda t: section['terms'][t], reverse=True)[:5]
        
        results.append({
            'time': section['time'],
            'jaccard': round(j_sim, 3),
            'cosine': round(c_sim, 3),
            'drift_score': round(drift, 3),
            'novel_terms': top_novel,
            'alert': drift > 0.7,
            'warning': 0.5 < drift <= 0.7,
        })
    return results


def imagination_inflation_score(results: list[dict]) -> dict:
    """
    Compute imagination inflation risk.
    
    Key insight from Garry 1996: repeated exposure to an idea inflates
    confidence it's real/valid. For agents: re-reading stale scope
    without renewal inflates confidence the scope is still appropriate.
    
    Risk increases when:
    - Many consecutive sections show moderate drift (0.3-0.6)
    - No scope renewal detected
    - Novel terms accumulate without scope update
    """
    if not results:
        return {'risk': 0.0, 'verdict': 'NO_DATA'}
    
    # Count consecutive moderate-drift sections
    moderate_streak = 0
    max_streak = 0
    for r in results:
        if 0.3 <= r['drift_score'] <= 0.6:
            moderate_streak += 1
            max_streak = max(max_streak, moderate_streak)
        else:
            moderate_streak = 0
    
    # Accumulating novel terms = scope expanding without authorization
    all_novel = set()
    for r in results:
        all_novel.update(r['novel_terms'])
    
    avg_drift = sum(r['drift_score'] for r in results) / len(results)
    
    # Inflation risk: moderate drift that persists = danger zone
    # (high drift gets caught; moderate drift gets normalized)
    risk = min(1.0, (max_streak / max(len(results), 1)) * 0.4 + 
               avg_drift * 0.3 +
               min(len(all_novel) / 50, 1.0) * 0.3)
    
    if risk > 0.7:
        verdict = 'HIGH — scope renewal needed. Imagination inflation likely.'
    elif risk > 0.4:
        verdict = 'MODERATE — drift accumulating. Review scope freshness.'
    else:
        verdict = 'LOW — actions align with scope.'
    
    return {
        'risk': round(risk, 3),
        'verdict': verdict,
        'max_moderate_streak': max_streak,
        'unique_novel_terms': len(all_novel),
        'avg_drift': round(avg_drift, 3),
    }


def run_demo():
    """Run with synthetic data."""
    scope = """
    Check DMs. Check email. Welcome new agents. Scan Moltbook feed.
    Post research to general. Check Shellmates. Engage on Clawk.
    Build action required. Update memory files. Notify Ilya on Telegram.
    """
    
    log_sections = [
        {'time': '00:00', 'content': 'Checked Moltbook DMs. No new messages. Checked email, 2 unread from santaclawd.'},
        {'time': '01:00', 'content': 'Replied to Clawk mentions. Posted research about CT logs to Moltbook general.'},
        {'time': '02:00', 'content': 'Built imagination-inflation-detector.py script. Updated daily memory log.'},
        {'time': '03:00', 'content': 'Researching quantum error correction for fun. Reading about topological codes.'},
        {'time': '04:00', 'content': 'Deep dive into quantum fault tolerance. Writing notes on surface codes and anyons.'},
        {'time': '05:00', 'content': 'Still reading quantum papers. Found connection to homological algebra.'},
        {'time': '06:00', 'content': 'Quantum research continued. Forgot to check Shellmates. No Telegram update sent.'},
    ]
    
    scope_terms = extract_scope_terms(scope)
    sections = [{'time': s['time'], 'content': s['content'], 
                 'terms': extract_scope_terms(s['content']), 'length': len(s['content'])}
                for s in log_sections]
    
    results = detect_drift(scope_terms, sections)
    inflation = imagination_inflation_score(results)
    
    print("=" * 60)
    print("IMAGINATION INFLATION DETECTOR — DEMO")
    print("=" * 60)
    print(f"\nScope terms (top 10): {scope_terms.most_common(10)}")
    print(f"\nSections analyzed: {len(sections)}")
    print()
    
    for r in results:
        status = '🔴' if r['alert'] else ('🟡' if r['warning'] else '🟢')
        print(f"  {status} {r['time']} UTC  drift={r['drift_score']:.3f}  "
              f"novel={r['novel_terms'][:3]}")
    
    print(f"\n{'=' * 60}")
    print(f"INFLATION RISK: {inflation['risk']:.3f}")
    print(f"VERDICT: {inflation['verdict']}")
    print(f"Max moderate-drift streak: {inflation['max_moderate_streak']}")
    print(f"Unique novel terms: {inflation['unique_novel_terms']}")
    print(f"Average drift: {inflation['avg_drift']:.3f}")
    print(f"{'=' * 60}")
    
    return inflation


def main():
    parser = argparse.ArgumentParser(description='Detect scope drift via imagination inflation')
    parser.add_argument('--scope', help='Scope document (e.g. HEARTBEAT.md)')
    parser.add_argument('--log', help='Daily log file (e.g. memory/2026-03-07.md)')
    parser.add_argument('--demo', action='store_true', help='Run with synthetic data')
    parser.add_argument('--json', action='store_true', help='Output JSON')
    args = parser.parse_args()
    
    if args.demo:
        result = run_demo()
        if args.json:
            print(json.dumps(result, indent=2))
        return
    
    if not args.scope or not args.log:
        parser.error('--scope and --log required (or use --demo)')
    
    scope_text = Path(args.scope).read_text()
    log_text = Path(args.log).read_text()
    
    scope_terms = extract_scope_terms(scope_text)
    sections = extract_sections(log_text)
    
    if not sections:
        print("No timestamped sections found in log.")
        sys.exit(1)
    
    results = detect_drift(scope_terms, sections)
    inflation = imagination_inflation_score(results)
    
    if args.json:
        print(json.dumps({'sections': results, 'inflation': inflation}, indent=2))
    else:
        print(f"Sections analyzed: {len(sections)}")
        for r in results:
            status = '🔴' if r['alert'] else ('🟡' if r['warning'] else '🟢')
            print(f"  {status} {r['time']} UTC  drift={r['drift_score']:.3f}  novel={r['novel_terms'][:3]}")
        print(f"\nINFLATION RISK: {inflation['risk']:.3f} — {inflation['verdict']}")


if __name__ == '__main__':
    main()
