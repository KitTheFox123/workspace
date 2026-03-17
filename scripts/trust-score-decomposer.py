#!/usr/bin/env python3
"""
trust-score-decomposer.py — Decompose opaque trust scores into auditable evidence.

"Trust score 87 means nothing if you don't know what 87 means."

An opaque score hides:
- Who measured it (single oracle vs independent witnesses)
- What was measured (delivery speed? quality? both?)
- When it was measured (fresh vs stale)
- How it was aggregated (mean? weighted? min?)

This tool takes an opaque score and shows what evidence WOULD be
needed to make it meaningful. Then compares evidence-based vs
opaque trust decisions.

Usage:
    python3 trust-score-decomposer.py
"""

import json
import math
from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class OpaqueScore:
    """What most platforms give you."""
    agent_id: str
    score: float  # 0-100
    source: str = "platform"
    # That's it. That's all you get.
    
    def decide(self, threshold: float = 70.0) -> str:
        return "TRUST" if self.score >= threshold else "REJECT"


@dataclass 
class EvidenceBasedScore:
    """What L3.5 receipts give you."""
    agent_id: str
    receipts: List[Dict] = field(default_factory=list)
    
    def summary(self) -> Dict:
        if not self.receipts:
            return {"error": "no_evidence"}
        
        n = len(self.receipts)
        
        # Dimension averages
        dims = {}
        for d in ['T', 'G', 'A', 'S', 'C']:
            vals = [r['dimensions'][d] for r in self.receipts if d in r.get('dimensions', {})]
            dims[d] = round(sum(vals) / len(vals), 3) if vals else 0
        
        # Witness analysis
        all_witnesses = []
        all_orgs = set()
        for r in self.receipts:
            for w in r.get('witnesses', []):
                all_witnesses.append(w)
                all_orgs.add(w.get('operator_id', 'unknown'))
        
        # Freshness
        timestamps = [r['timestamp'] for r in self.receipts]
        
        # Decision types
        types = {}
        for r in self.receipts:
            dt = r.get('decision_type', 'unknown')
            types[dt] = types.get(dt, 0) + 1
        
        return {
            'receipt_count': n,
            'dimensions': dims,
            'unique_witnesses': len(set(w.get('agent_id') for w in all_witnesses)),
            'unique_orgs': len(all_orgs),
            'org_diversity': round(len(all_orgs) / max(len(all_witnesses), 1), 3),
            'decision_types': types,
            'has_refusals': types.get('refusal', 0) > 0,
            'has_scars': any(r.get('scar_reference') for r in self.receipts),
        }
    
    def decide(self, policy: Dict) -> Dict:
        s = self.summary()
        issues = []
        
        if s.get('error'):
            return {'verdict': 'REJECT', 'reason': 'no_evidence'}
        
        min_receipts = policy.get('min_receipts', 3)
        if s['receipt_count'] < min_receipts:
            issues.append(f"insufficient_history: {s['receipt_count']} < {min_receipts}")
        
        min_orgs = policy.get('min_witness_orgs', 2)
        if s['unique_orgs'] < min_orgs:
            issues.append(f"low_witness_diversity: {s['unique_orgs']} orgs < {min_orgs}")
        
        for dim, threshold in policy.get('min_dimensions', {}).items():
            if s['dimensions'].get(dim, 0) < threshold:
                issues.append(f"{dim}_below_threshold: {s['dimensions'].get(dim, 0)} < {threshold}")
        
        return {
            'verdict': 'REJECT' if issues else 'TRUST',
            'issues': issues,
            'evidence': s,
            'auditable': True,
        }


def demo():
    print("=" * 60)
    print("TRUST SCORE DECOMPOSITION")
    print("'87 means nothing without provenance'")
    print("=" * 60)
    
    # Scenario 1: Opaque score looks great
    opaque = OpaqueScore("agent:scammer", 92.0, "platform_x")
    print(f"\n--- OPAQUE SCORE ---")
    print(f"Agent: {opaque.agent_id}")
    print(f"Score: {opaque.score}")
    print(f"Source: {opaque.source}")
    print(f"Decision: {opaque.decide()}")
    print(f"Can you audit this? NO")
    print(f"Do you know who measured it? NO")
    print(f"Do you know when? NO")
    print(f"Do you know the methodology? NO")
    
    # Scenario 2: Same agent, evidence-based
    evidence = EvidenceBasedScore("agent:scammer", [
        {
            'decision_type': 'delivery',
            'timestamp': '2026-03-17T09:00:00Z',
            'dimensions': {'T': 0.95, 'G': 0.30, 'A': 0.90, 'S': 0.20, 'C': 0.85},
            'witnesses': [
                {'agent_id': 'w1', 'operator_id': 'org:same_owner'},
                {'agent_id': 'w2', 'operator_id': 'org:same_owner'},
            ],
        },
        {
            'decision_type': 'delivery',
            'timestamp': '2026-03-17T09:01:00Z',
            'dimensions': {'T': 0.98, 'G': 0.25, 'A': 0.88, 'S': 0.15, 'C': 0.82},
            'witnesses': [
                {'agent_id': 'w1', 'operator_id': 'org:same_owner'},
            ],
        },
    ])
    
    policy = {
        'min_receipts': 3,
        'min_witness_orgs': 2,
        'min_dimensions': {'G': 0.50, 'S': 0.40},
    }
    
    result = evidence.decide(policy)
    print(f"\n--- EVIDENCE-BASED ---")
    print(f"Agent: {evidence.agent_id}")
    print(f"Decision: {result['verdict']}")
    print(f"Issues found: {len(result['issues'])}")
    for issue in result['issues']:
        print(f"  ⚠️  {issue}")
    print(f"\nEvidence summary:")
    s = result['evidence']
    print(f"  Receipts: {s['receipt_count']}")
    print(f"  Witness orgs: {s['unique_orgs']} (diversity: {s['org_diversity']})")
    print(f"  Groundedness: {s['dimensions']['G']} ← RED FLAG")
    print(f"  Self-knowledge: {s['dimensions']['S']} ← RED FLAG")
    print(f"  Has refusals: {s['has_refusals']} (no principled refusals = suspicious)")
    print(f"  Auditable: {result['auditable']}")
    
    # The contrast
    print(f"\n{'=' * 60}")
    print("COMPARISON")
    print(f"{'=' * 60}")
    print(f"\n  Opaque score 92 → TRUST (wrong!)")
    print(f"  Evidence-based → REJECT (correct!)")
    print(f"\n  The opaque score HID:")
    print(f"  - All witnesses from same org (sybil risk)")
    print(f"  - Groundedness 0.28 (makes things up)")
    print(f"  - Self-knowledge 0.18 (doesn't know what it doesn't know)")
    print(f"  - Zero refusals (always says yes = no principles)")
    print(f"  - Only 2 receipts (insufficient history)")
    print(f"\n  The number 92 was technically correct.")
    print(f"  It was also completely misleading.")
    print(f"  Evidence > scores. Always.")


if __name__ == '__main__':
    demo()
