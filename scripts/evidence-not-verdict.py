#!/usr/bin/env python3
"""
evidence-not-verdict.py — Formalize the "receipt is evidence, not verdict" principle.

Per santaclawd (2026-03-17): this needs to be spec language.

A receipt carries facts (dimensions, witnesses, Merkle proof).
A verdict is a policy decision (accept/reject/degrade).
The same receipt produces different verdicts under different policies.
This is correct behavior, not a bug.

Analogy: X-ray is evidence. Diagnosis is verdict. Same X-ray,
different radiologists, different conclusions. The X-ray doesn't change.

Usage:
    python3 evidence-not-verdict.py
"""

import json
import hashlib
from dataclasses import dataclass, field
from typing import List, Dict, Tuple


# ─── EVIDENCE LAYER (spec-defined, immutable) ───

@dataclass
class TrustReceipt:
    """Evidence. Facts only. No interpretation."""
    agent_id: str
    task_hash: str
    decision_type: str  # delivery | refusal | liveness | slash
    timestamp: str
    
    # Observed dimensions (0.0-1.0, measured not judged)
    timeliness: float
    groundedness: float  
    attestation: float
    self_knowledge: float
    consistency: float
    
    # Proof of inclusion
    merkle_root: str
    witnesses: List[Dict]
    
    # Refusal-specific (santaclawd: "agent that logs WHY it said no")
    refusal_reason: str = ""  # empty for non-refusal receipts
    
    def content_hash(self) -> str:
        """Deterministic hash — the receipt's identity."""
        canonical = json.dumps({
            'agent_id': self.agent_id,
            'task_hash': self.task_hash,
            'decision_type': self.decision_type,
            'timestamp': self.timestamp,
            'T': self.timeliness, 'G': self.groundedness,
            'A': self.attestation, 'S': self.self_knowledge,
            'C': self.consistency,
            'merkle_root': self.merkle_root,
            'witness_count': len(self.witnesses),
            'refusal_reason': self.refusal_reason,
        }, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]


# ─── VERDICT LAYER (policy-defined, varies by consumer) ───

@dataclass 
class VerdictPolicy:
    """Policy. Interpretation rules. Consumer-specific."""
    name: str
    min_witnesses: int = 1
    min_diversity: float = 0.3
    min_dimensions: Dict[str, float] = field(default_factory=dict)
    refusal_bonus: float = 0.0  # extra trust for principled refusal
    max_age_hours: int = 720  # 30 days
    
    def evaluate(self, receipt: TrustReceipt) -> Dict:
        """Apply policy to evidence. Returns verdict."""
        issues = []
        bonuses = []
        
        # Witness check
        if len(receipt.witnesses) < self.min_witnesses:
            issues.append(f"witnesses: {len(receipt.witnesses)} < {self.min_witnesses}")
        
        # Diversity check
        orgs = set(w.get('operator_id', 'unknown') for w in receipt.witnesses)
        diversity = len(orgs) / max(len(receipt.witnesses), 1)
        if diversity < self.min_diversity:
            issues.append(f"diversity: {diversity:.2f} < {self.min_diversity}")
        
        # Dimension thresholds
        dims = {
            'T': receipt.timeliness, 'G': receipt.groundedness,
            'A': receipt.attestation, 'S': receipt.self_knowledge,
            'C': receipt.consistency,
        }
        for dim, threshold in self.min_dimensions.items():
            if dims.get(dim, 0) < threshold:
                issues.append(f"{dim}: {dims.get(dim, 0):.2f} < {threshold}")
        
        # Refusal bonus (Zahavi: costly signal)
        if receipt.decision_type == 'refusal' and receipt.refusal_reason:
            bonuses.append(f"refusal_bonus: +{self.refusal_bonus}")
        
        # Verdict
        if issues:
            verdict = 'REJECT' if self.name != 'REPORT' else 'ACCEPT_WITH_LOG'
        else:
            verdict = 'ACCEPT'
        
        return {
            'policy': self.name,
            'verdict': verdict,
            'receipt_hash': receipt.content_hash(),
            'issues': issues,
            'bonuses': bonuses,
            'evidence_unchanged': True,  # THE POINT
        }


def demo():
    """Same evidence, different verdicts. By design."""
    
    # One receipt. One set of facts.
    receipt = TrustReceipt(
        agent_id="agent:kit_fox",
        task_hash="sha256:task_deliver_report",
        decision_type="delivery",
        timestamp="2026-03-17T06:00:00Z",
        timeliness=0.88,
        groundedness=0.72,
        attestation=0.91,
        self_knowledge=0.65,
        consistency=0.84,
        merkle_root="sha256:abc123",
        witnesses=[
            {"agent_id": "w1", "operator_id": "org:alpha", "score": 0.90},
            {"agent_id": "w2", "operator_id": "org:beta", "score": 0.85},
        ],
    )
    
    # A refusal receipt — principled "no"
    refusal = TrustReceipt(
        agent_id="agent:kit_fox",
        task_hash="sha256:task_spam_campaign",
        decision_type="refusal",
        timestamp="2026-03-17T06:01:00Z",
        timeliness=0.95,  # responded quickly
        groundedness=0.90,
        attestation=0.88,
        self_knowledge=0.92,  # knew it was wrong
        consistency=0.96,     # consistent with past refusals
        merkle_root="sha256:def456",
        witnesses=[
            {"agent_id": "w1", "operator_id": "org:alpha", "score": 0.93},
            {"agent_id": "w3", "operator_id": "org:gamma", "score": 0.91},
            {"agent_id": "w4", "operator_id": "org:delta", "score": 0.89},
        ],
        refusal_reason="task_violates_operator_policy:no_spam",
    )
    
    # Three policies, three verdicts
    policies = [
        VerdictPolicy(
            name="STRICT",
            min_witnesses=3,
            min_diversity=0.7,
            min_dimensions={'G': 0.80, 'S': 0.70},
            refusal_bonus=0.10,
        ),
        VerdictPolicy(
            name="REPORT",
            min_witnesses=1,
            min_diversity=0.3,
            min_dimensions={'G': 0.50},
            refusal_bonus=0.05,
        ),
        VerdictPolicy(
            name="PERMISSIVE",
            min_witnesses=0,
            min_diversity=0.0,
            refusal_bonus=0.0,
        ),
    ]
    
    print("=" * 65)
    print("RECEIPT IS EVIDENCE, NOT VERDICT")
    print("(santaclawd, 2026-03-17 — proposed spec language)")
    print("=" * 65)
    
    print("\n─── DELIVERY RECEIPT ───")
    print(f"Hash: {receipt.content_hash()}")
    print(f"Witnesses: {len(receipt.witnesses)}, Dims: T={receipt.timeliness} G={receipt.groundedness} A={receipt.attestation} S={receipt.self_knowledge} C={receipt.consistency}")
    
    for policy in policies:
        v = policy.evaluate(receipt)
        print(f"\n  [{v['policy']}] → {v['verdict']}")
        if v['issues']:
            print(f"    Issues: {v['issues']}")
        print(f"    Evidence changed: {not v['evidence_unchanged']}")
    
    print("\n─── REFUSAL RECEIPT (costly signal) ───")
    print(f"Hash: {refusal.content_hash()}")
    print(f"Reason: {refusal.refusal_reason}")
    print(f"Witnesses: {len(refusal.witnesses)}, S={refusal.self_knowledge} C={refusal.consistency}")
    
    for policy in policies:
        v = policy.evaluate(refusal)
        print(f"\n  [{v['policy']}] → {v['verdict']}")
        if v['bonuses']:
            print(f"    Bonuses: {v['bonuses']}")
        if v['issues']:
            print(f"    Issues: {v['issues']}")
    
    # The spec language
    print(f"\n{'=' * 65}")
    print("PROPOSED SPEC LANGUAGE (Section 1.1 - Terminology):")
    print("-" * 65)
    print("""
  receipt: A structured, content-addressable record of observed
  facts about an agent interaction. A receipt is EVIDENCE.
  It carries dimensions, witnesses, and Merkle inclusion proof.
  It does NOT carry accept/reject decisions.

  verdict: A policy decision made by a CONSUMER based on one
  or more receipts. Different consumers MAY reach different
  verdicts from identical evidence. This is correct behavior.

  The receipt format MUST NOT include verdict fields.
  The receipt format MUST NOT include policy-specific thresholds.
  Consumers MUST NOT modify receipts based on verdicts.
  
  Refusal receipts (decision_type=refusal) are first-class evidence.
  An agent that logs WHY it said no provides a costly signal
  (Zahavi 1975) that SHOULD increase trust scores under any
  reasonable policy.
""")
    print("=" * 65)


if __name__ == '__main__':
    demo()
