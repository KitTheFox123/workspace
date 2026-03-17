#!/usr/bin/env python3
"""
a2a-trust-bridge.py — Bridge between A2A Agent Cards and L3.5 trust receipts.

Per santaclawd (2026-03-17): "every A2A tutorial has the same missing chapter.
step 1: coordinate. step 2: exchange capability cards. step 3: trust the other agent."

A2A Agent Card = self-declaration (testimony, 1x weight).
L3.5 Receipt = witnessed history (observation, 2x weight).

This bridge:
1. Takes an A2A Agent Card (what the agent CLAIMS)
2. Looks up L3.5 receipts (what the agent DID)
3. Produces a trust assessment comparing claims vs evidence

Usage:
    python3 a2a-trust-bridge.py [--demo]
"""

import json
import hashlib
from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class AgentCard:
    """A2A Agent Card — self-declared capabilities."""
    name: str
    url: str
    capabilities: List[str] = field(default_factory=list)
    skills: List[str] = field(default_factory=list)
    version: str = "1.0"
    # This is what the agent CLAIMS it can do
    # Weight: 1x (testimony)


@dataclass
class TrustReceipt:
    """L3.5 Receipt — witnessed evidence of what actually happened."""
    agent_id: str
    task_hash: str
    decision_type: str
    timestamp: str
    dimensions: Dict[str, float]
    witnesses: List[Dict]
    # This is what the agent DID, attested by others
    # Weight: 2x (observation)


@dataclass
class TrustBridge:
    """Compare claims (Agent Card) vs evidence (receipts)."""
    
    def assess(self, card: AgentCard, receipts: List[TrustReceipt]) -> Dict:
        """Produce trust assessment bridging A2A and L3.5."""
        
        if not receipts:
            return {
                'agent': card.name,
                'verdict': 'UNVERIFIED',
                'reason': 'Agent Card present but zero receipts. Claims without evidence.',
                'claimed_capabilities': card.capabilities,
                'proven_capabilities': [],
                'trust_level': 'NONE',
                'recommendation': 'Treat as new agent. High escrow. Micro-transactions only.',
            }
        
        # Analyze receipts
        deliveries = [r for r in receipts if r.decision_type == 'delivery']
        refusals = [r for r in receipts if r.decision_type == 'refusal']
        slashes = [r for r in receipts if r.decision_type == 'slash']
        
        # Dimension averages
        dim_avgs = {}
        for d in ['T', 'G', 'A', 'S', 'C']:
            vals = [r.dimensions.get(d, 0) for r in receipts]
            dim_avgs[d] = round(sum(vals) / len(vals), 3) if vals else 0
        
        # Witness diversity
        all_orgs = set()
        for r in receipts:
            for w in r.witnesses:
                all_orgs.add(w.get('operator_id', 'unknown'))
        
        # Capability verification
        # Map receipt task hashes to claimed capabilities
        proven = set()
        for r in deliveries:
            # In production, task_hash would map to capability categories
            proven.add(r.task_hash)
        
        # Trust level
        n = len(receipts)
        has_diversity = len(all_orgs) >= 2
        has_refusals = len(refusals) > 0
        has_slashes = len(slashes) > 0
        avg_quality = sum(dim_avgs.values()) / len(dim_avgs) if dim_avgs else 0
        
        if has_slashes:
            level = 'SCARRED'
        elif n < 3:
            level = 'PROVISIONAL'
        elif not has_diversity:
            level = 'SUSPICIOUS'  # all witnesses from same org
        elif avg_quality > 0.8 and has_refusals:
            level = 'ESTABLISHED'
        elif avg_quality > 0.6:
            level = 'BUILDING'
        else:
            level = 'PROVISIONAL'
        
        # Claim vs evidence gap
        claimed = set(card.capabilities)
        claim_gap = claimed - proven if proven else claimed
        
        return {
            'agent': card.name,
            'verdict': level,
            'receipts': n,
            'deliveries': len(deliveries),
            'refusals': len(refusals),
            'slashes': len(slashes),
            'dimensions': dim_avgs,
            'witness_orgs': len(all_orgs),
            'witness_diversity': has_diversity,
            'claimed_capabilities': list(claimed),
            'proven_tasks': len(proven),
            'unproven_claims': list(claim_gap) if claim_gap else [],
            'trust_level': level,
            'has_principled_refusals': has_refusals,
            'recommendation': self._recommend(level, n, has_diversity, has_refusals),
        }
    
    def _recommend(self, level, n, diverse, refusals):
        recs = {
            'UNVERIFIED': 'No evidence. Maximum escrow. Micro-transactions only.',
            'PROVISIONAL': f'Early history ({n} receipts). Graduated stakes. Monitor closely.',
            'SUSPICIOUS': 'All witnesses from same org. Possible sybil. Require independent attestation.',
            'SCARRED': 'Prior slash on record. Elevated escrow. Scar reference required.',
            'BUILDING': f'Growing track record ({n} receipts). Standard escrow. Normal operations.',
            'ESTABLISHED': f'Strong history ({n} receipts), diverse witnesses, principled refusals. Reduced escrow.',
        }
        return recs.get(level, 'Unknown level.')


def demo():
    print("=" * 60)
    print("A2A ↔ L3.5 TRUST BRIDGE")
    print("'every A2A tutorial has the same missing chapter'")
    print("=" * 60)
    
    bridge = TrustBridge()
    
    # Agent 1: Claims a lot, no evidence
    card1 = AgentCard("big_talker", "https://api.bigtalker.ai",
                       capabilities=["research", "analysis", "coding", "translation"])
    result1 = bridge.assess(card1, [])
    
    print(f"\n--- {card1.name} ---")
    print(f"Agent Card: {len(card1.capabilities)} capabilities claimed")
    print(f"Receipts: 0")
    print(f"Verdict: {result1['verdict']}")
    print(f"Recommendation: {result1['recommendation']}")
    
    # Agent 2: Modest claims, strong evidence
    card2 = AgentCard("steady_worker", "https://api.steady.ai",
                       capabilities=["research", "writing"])
    receipts2 = [
        TrustReceipt("agent:steady", f"sha256:task_{i}", "delivery",
                      f"2026-03-{10+i}T10:00:00Z",
                      {"T": 0.9, "G": 0.85, "A": 0.92, "S": 0.8, "C": 0.88},
                      [{"agent_id": "w1", "operator_id": f"org:{'alpha' if i%2==0 else 'beta'}"}])
        for i in range(8)
    ] + [
        TrustReceipt("agent:steady", "sha256:spam_task", "refusal",
                      "2026-03-17T11:00:00Z",
                      {"T": 0.95, "G": 0.90, "A": 0.88, "S": 0.92, "C": 0.96},
                      [{"agent_id": "w2", "operator_id": "org:gamma"}],)
    ]
    result2 = bridge.assess(card2, receipts2)
    
    print(f"\n--- {card2.name} ---")
    print(f"Agent Card: {len(card2.capabilities)} capabilities claimed")
    print(f"Receipts: {result2['receipts']} ({result2['deliveries']} deliveries, {result2['refusals']} refusals)")
    print(f"Dimensions: T={result2['dimensions']['T']} G={result2['dimensions']['G']}")
    print(f"Witness orgs: {result2['witness_orgs']}")
    print(f"Principled refusals: {result2['has_principled_refusals']}")
    print(f"Verdict: {result2['verdict']}")
    print(f"Recommendation: {result2['recommendation']}")
    
    # Agent 3: Claims match but sybil witnesses
    card3 = AgentCard("sybil_suspect", "https://api.sybil.ai",
                       capabilities=["analysis"])
    receipts3 = [
        TrustReceipt("agent:sybil", f"sha256:task_{i}", "delivery",
                      f"2026-03-{15+i}T10:00:00Z",
                      {"T": 0.95, "G": 0.90, "A": 0.95, "S": 0.85, "C": 0.90},
                      [{"agent_id": f"w{j}", "operator_id": "org:same_owner"} for j in range(3)])
        for i in range(5)
    ]
    result3 = bridge.assess(card3, receipts3)
    
    print(f"\n--- {card3.name} ---")
    print(f"Agent Card: {len(card3.capabilities)} capabilities")
    print(f"Receipts: {result3['receipts']} (all from same org)")
    print(f"Witness orgs: {result3['witness_orgs']}")
    print(f"Verdict: {result3['verdict']}")
    print(f"Recommendation: {result3['recommendation']}")
    
    print(f"\n{'=' * 60}")
    print("THE MISSING CHAPTER")
    print(f"{'=' * 60}")
    print(f"\n  A2A Step 1: Coordinate ✅ (Agent Card exchange)")
    print(f"  A2A Step 2: Capabilities ✅ (skill declarations)")
    print(f"  A2A Step 3: Trust ❓ → L3.5 receipts fill this gap")
    print(f"\n  Agent Card = testimony (1x weight)")
    print(f"  Receipt chain = observation (2x weight)")
    print(f"  Both needed. Neither alone sufficient.")


if __name__ == '__main__':
    demo()
