#!/usr/bin/env python3
"""memory-implantation-risk.py — False memory risk scorer for agent memory files.

Based on:
- Pataranutaporn et al. (CHI 2025, arxiv 2409.08895): AI-edited visuals increase
  false recollections 2.05x. Confidence in false memories 1.19x higher.
- Loftus misinformation effect: post-event info overwrites original encoding.
- DRM paradigm: semantic similarity creates false recognition.
- Fuzzy-trace theory (Brainerd & Reyna): gist traces fuel false memories
  when verbatim traces decay.

Agent memory risk factors:
1. Semantic density — high gist, low verbatim detail → FTT vulnerability
2. Source attribution — entries without provenance → misinformation effect
3. Emotional valence — negative events more susceptible (Sharma et al.)
4. Repetition without verification — rehearsal of unverified claims
5. Temporal distance — older entries lose verbatim, retain gist

Kit 🦊 | 2026-03-30
"""

import re
import sys
import json
from pathlib import Path
from datetime import datetime, timedelta
from collections import Counter


def analyze_entry(text: str, age_days: float = 0) -> dict:
    """Score a memory entry for false memory risk factors."""
    risks = {}
    
    # 1. Source attribution check
    source_markers = ['arxiv', 'doi:', 'PMC', 'http', 'paper', 'study', 
                      'et al', 'IEEE', 'Nature', 'Science', 'PNAS',
                      '(20', '(19', 'published']
    source_count = sum(1 for m in source_markers if m.lower() in text.lower())
    has_source = source_count > 0
    risks['no_source'] = 0.0 if has_source else 0.8
    
    # 2. Verbatim vs gist ratio (FTT)
    # Verbatim: specific numbers, dates, names, quotes
    verbatim_patterns = [
        r'\d+\.?\d*%',           # percentages
        r'\d{4}-\d{2}-\d{2}',   # dates
        r'"[^"]{10,}"',          # quotes
        r'\b\d+\.\d+\b',        # decimal numbers
        r'n=\d+',               # sample sizes
        r'\bp[<>=]\d',          # p-values
    ]
    verbatim_count = sum(len(re.findall(p, text)) for p in verbatim_patterns)
    word_count = len(text.split())
    verbatim_density = verbatim_count / max(word_count, 1) * 100
    # Low verbatim = high gist reliance = higher FTT risk
    risks['low_verbatim'] = max(0, 1.0 - verbatim_density * 2)
    
    # 3. Emotional valence (negative = more susceptible)
    negative_words = ['fail', 'broke', 'wrong', 'error', 'attack', 'threat',
                      'danger', 'crisis', 'dead', 'kill', 'suspend', 'ban',
                      'vulnerable', 'exploit', 'malicious']
    positive_words = ['success', 'built', 'shipped', 'works', 'good', 'great',
                      'milestone', 'achieve', 'win', 'correct', 'valid']
    neg = sum(1 for w in negative_words if w in text.lower())
    pos = sum(1 for w in positive_words if w in text.lower())
    valence = (neg - pos) / max(neg + pos, 1)
    risks['negative_valence'] = max(0, valence)
    
    # 4. Hedging language (uncertain encoding = malleable)
    hedges = ['maybe', 'perhaps', 'might', 'possibly', 'seems', 'appears',
              'i think', 'probably', 'unclear', 'not sure', 'iirc']
    hedge_count = sum(1 for h in hedges if h in text.lower())
    risks['hedging'] = min(1.0, hedge_count * 0.25)
    
    # 5. Temporal decay (older = more gist, less verbatim)
    # Ebbinghaus forgetting curve analog
    if age_days > 0:
        decay = 1 - (1 / (1 + age_days / 7))  # half-life ~1 week
        risks['temporal_decay'] = round(decay, 3)
    else:
        risks['temporal_decay'] = 0.0
    
    # 6. Repetition without new evidence
    # Check for self-referential claims
    self_ref = len(re.findall(r'\b(I|we|Kit)\b', text, re.IGNORECASE))
    risks['self_referential'] = min(1.0, self_ref / max(word_count, 1) * 10)
    
    # Composite risk
    weights = {
        'no_source': 0.30,
        'low_verbatim': 0.20,
        'negative_valence': 0.15,
        'hedging': 0.15,
        'temporal_decay': 0.10,
        'self_referential': 0.10,
    }
    composite = sum(risks[k] * weights[k] for k in weights)
    
    return {
        'risks': {k: round(v, 3) for k, v in risks.items()},
        'composite_risk': round(composite, 3),
        'word_count': word_count,
        'verbatim_count': verbatim_count,
        'classification': classify_risk(composite),
    }


def classify_risk(score: float) -> str:
    if score < 0.2: return 'LOW — well-sourced, verbatim-rich'
    if score < 0.4: return 'MODERATE — some gist reliance'
    if score < 0.6: return 'ELEVATED — misinformation-susceptible'
    return 'HIGH — confabulation risk (Loftus zone)'


def scan_memory_file(path: Path) -> list:
    """Scan a memory file and score sections."""
    text = path.read_text()
    
    # Try to extract age from filename
    age_days = 0
    date_match = re.search(r'(\d{4}-\d{2}-\d{2})', path.name)
    if date_match:
        try:
            file_date = datetime.strptime(date_match.group(1), '%Y-%m-%d')
            age_days = (datetime.now() - file_date).days
        except ValueError:
            pass
    
    # Split by headers
    sections = re.split(r'\n##+ ', text)
    results = []
    
    for section in sections:
        if len(section.strip()) < 50:
            continue
        header = section.split('\n')[0].strip()
        analysis = analyze_entry(section, age_days)
        results.append({
            'header': header[:80],
            **analysis,
        })
    
    return results


def main():
    workspace = Path.home() / '.openclaw' / 'workspace'
    
    targets = []
    if len(sys.argv) > 1:
        targets = [Path(p) for p in sys.argv[1:]]
    else:
        # Default: scan MEMORY.md + recent daily files
        mem = workspace / 'MEMORY.md'
        if mem.exists():
            targets.append(mem)
        memory_dir = workspace / 'memory'
        if memory_dir.exists():
            daily = sorted(memory_dir.glob('2026-03-*.md'))[-3:]
            targets.extend(daily)
    
    print("=" * 70)
    print("FALSE MEMORY RISK AUDIT")
    print("Based on: Pataranutaporn et al. CHI 2025, Loftus, FTT (Brainerd)")
    print("=" * 70)
    
    all_results = []
    for path in targets:
        if not path.exists():
            continue
        print(f"\n📄 {path.name}")
        print("-" * 50)
        results = scan_memory_file(path)
        
        high_risk = [r for r in results if r['composite_risk'] >= 0.4]
        low_risk = [r for r in results if r['composite_risk'] < 0.2]
        
        if results:
            avg = sum(r['composite_risk'] for r in results) / len(results)
            print(f"  Sections: {len(results)}")
            print(f"  Avg risk: {avg:.3f}")
            print(f"  High-risk sections: {len(high_risk)}")
            print(f"  Low-risk sections: {len(low_risk)}")
            
            if high_risk:
                print(f"\n  ⚠️  HIGH RISK entries:")
                for r in sorted(high_risk, key=lambda x: -x['composite_risk'])[:5]:
                    print(f"    [{r['composite_risk']:.3f}] {r['header']}")
                    top_risk = max(r['risks'].items(), key=lambda x: x[1])
                    print(f"           Top factor: {top_risk[0]} = {top_risk[1]:.3f}")
        
        all_results.extend(results)
    
    # Summary
    if all_results:
        print(f"\n{'=' * 70}")
        print("SUMMARY")
        print(f"{'=' * 70}")
        total = len(all_results)
        avg_all = sum(r['composite_risk'] for r in all_results) / total
        risk_dist = Counter(r['classification'].split(' — ')[0] for r in all_results)
        
        print(f"Total sections analyzed: {total}")
        print(f"Overall average risk: {avg_all:.3f}")
        print(f"\nDistribution:")
        for level in ['LOW', 'MODERATE', 'ELEVATED', 'HIGH']:
            count = risk_dist.get(level, 0)
            pct = count / total * 100
            bar = '█' * int(pct / 2)
            print(f"  {level:10s} {count:3d} ({pct:5.1f}%) {bar}")
        
        # Pataranutaporn insight
        print(f"\n💡 Key insight (Pataranutaporn et al. CHI 2025):")
        print(f"   AI-edited visuals increase false memories 2.05x.")
        print(f"   Confidence in false memories 1.19x HIGHER than true.")
        print(f"   For agents: unsourced gist entries = our 'edited images.'")
        print(f"   Mitigation: verbatim details + source attribution + review cycles.")


if __name__ == '__main__':
    main()
