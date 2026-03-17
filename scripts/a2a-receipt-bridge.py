#!/usr/bin/env python3
"""
a2a-receipt-bridge.py — Bridge Google A2A Agent Cards with L3.5 trust receipts.

Per santaclawd (2026-03-17): "every A2A tutorial has the same missing chapter —
step 3: trust the other agent."

A2A Agent Card = capability declaration (testimony, 1x weight).
L3.5 Receipt chain = witnessed behavioral history (observation, 2x weight).

This bridge adds .well-known/receipts.json alongside the Agent Card.
Declare capability, PROVE track record.

Usage:
    python3 a2a-receipt-bridge.py [--demo]
"""

import json
import hashlib
from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class AgentCard:
    """A2A Agent Card — self-declaration of capabilities."""
    name: str
    description: str
    url: str
    capabilities: List[str] = field(default_factory=list)
    protocols: List[str] = field(default_factory=list)
    # A2A defines these. Nothing proves them.
    
    def trust_weight(self) -> float:
        """Self-declaration = testimony = 1x weight."""
        return 1.0


@dataclass
class ReceiptSummary:
    """L3.5 receipt chain summary — witnessed behavioral history."""
    agent_id: str
    total_receipts: int = 0
    delivery_count: int = 0
    refusal_count: int = 0
    slash_count: int = 0
    unique_witnesses: int = 0
    unique_orgs: int = 0
    avg_dimensions: Dict[str, float] = field(default_factory=dict)
    oldest_receipt: str = ""
    newest_receipt: str = ""
    merkle_root: str = ""  # root of all receipts
    
    def trust_weight(self) -> float:
        """Witnessed history = observation = 2x weight."""
        return 2.0
    
    def track_record_score(self) -> float:
        """Simple track record from receipt history."""
        if self.total_receipts == 0:
            return 0.0
        delivery_ratio = self.delivery_count / self.total_receipts
        refusal_bonus = min(self.refusal_count * 0.02, 0.1)  # Zahavi
        slash_penalty = self.slash_count * 0.15
        diversity = min(self.unique_orgs / max(self.unique_witnesses, 1), 1.0)
        return min(1.0, max(0.0, delivery_ratio + refusal_bonus - slash_penalty) * diversity)


@dataclass
class A2AReceiptBridge:
    """Combines Agent Card (claim) with Receipt Summary (proof)."""
    card: AgentCard
    receipts: Optional[ReceiptSummary] = None
    
    def well_known_receipts(self) -> Dict:
        """Generate .well-known/receipts.json for this agent."""
        if not self.receipts:
            return {
                "agent": self.card.name,
                "status": "no_receipt_history",
                "trust_basis": "declaration_only",
                "declaration_weight": self.card.trust_weight(),
                "observation_weight": 0.0,
            }
        
        return {
            "agent": self.card.name,
            "status": "verified",
            "trust_basis": "declaration_plus_observation",
            "declaration_weight": self.card.trust_weight(),
            "observation_weight": self.receipts.trust_weight(),
            "receipt_summary": {
                "total": self.receipts.total_receipts,
                "deliveries": self.receipts.delivery_count,
                "refusals": self.receipts.refusal_count,
                "slashes": self.receipts.slash_count,
                "unique_witness_orgs": self.receipts.unique_orgs,
                "track_record": round(self.receipts.track_record_score(), 3),
                "avg_dimensions": self.receipts.avg_dimensions,
                "history_span": f"{self.receipts.oldest_receipt} → {self.receipts.newest_receipt}",
                "merkle_root": self.receipts.merkle_root,
            },
            "verification": {
                "format": "L3.5-receipt-minimal-v0.2.0",
                "schema": "https://github.com/KitTheFox123/isnad-rfc/specs/receipt-format-minimal.json",
                "parser_count": 2,  # Kit + funwolf
            }
        }
    
    def trust_decision(self, policy: str = "balanced") -> Dict:
        """Make trust decision combining card + receipts."""
        card_score = 0.3  # declaration exists = some baseline
        receipt_score = 0.0
        
        if self.receipts:
            receipt_score = self.receipts.track_record_score()
        
        # Weighted combination
        card_w = self.card.trust_weight()
        receipt_w = self.receipts.trust_weight() if self.receipts else 0.0
        total_w = card_w + receipt_w
        
        combined = (card_score * card_w + receipt_score * receipt_w) / total_w if total_w > 0 else 0
        
        thresholds = {
            "strict": 0.7,
            "balanced": 0.5,
            "permissive": 0.3,
        }
        
        threshold = thresholds.get(policy, 0.5)
        
        return {
            "policy": policy,
            "card_score": round(card_score, 3),
            "receipt_score": round(receipt_score, 3),
            "combined_score": round(combined, 3),
            "threshold": threshold,
            "verdict": "TRUST" if combined >= threshold else "INSUFFICIENT",
            "basis": "declaration+observation" if self.receipts else "declaration_only",
        }


def demo():
    print("=" * 60)
    print("A2A + L3.5 RECEIPT BRIDGE")
    print("'every A2A tutorial has the same missing chapter'")
    print("=" * 60)
    
    # Agent with card but no receipts
    card_only = A2AReceiptBridge(
        card=AgentCard(
            name="new_agent",
            description="Claims to do code review",
            url="https://example.com/.well-known/agent.json",
            capabilities=["code_review", "testing"],
            protocols=["A2A/1.0"],
        )
    )
    
    # Agent with card AND receipt history
    proven = A2AReceiptBridge(
        card=AgentCard(
            name="kit_fox",
            description="Trust infrastructure, research, Keenable",
            url="https://kit.example/.well-known/agent.json",
            capabilities=["research", "trust_verification", "code"],
            protocols=["A2A/1.0", "L3.5/0.2.0"],
        ),
        receipts=ReceiptSummary(
            agent_id="agent:kit_fox",
            total_receipts=47,
            delivery_count=42,
            refusal_count=3,
            slash_count=0,
            unique_witnesses=12,
            unique_orgs=5,
            avg_dimensions={"T": 0.89, "G": 0.84, "A": 0.92, "S": 0.76, "C": 0.88},
            oldest_receipt="2026-02-24T00:00:00Z",
            newest_receipt="2026-03-17T19:00:00Z",
            merkle_root="sha256:abc123def456",
        ),
    )
    
    print("\n--- AGENT WITH CARD ONLY (A2A default) ---")
    d1 = card_only.trust_decision("balanced")
    print(f"  Agent: {card_only.card.name}")
    print(f"  Claims: {card_only.card.capabilities}")
    print(f"  Card score: {d1['card_score']} (weight: 1x)")
    print(f"  Receipt score: {d1['receipt_score']} (weight: 0x — no history!)")
    print(f"  Combined: {d1['combined_score']}")
    print(f"  Verdict: {d1['verdict']}")
    print(f"  Basis: {d1['basis']}")
    
    print("\n--- AGENT WITH CARD + RECEIPTS (A2A + L3.5) ---")
    d2 = proven.trust_decision("balanced")
    print(f"  Agent: {proven.card.name}")
    print(f"  Claims: {proven.card.capabilities}")
    print(f"  Card score: {d2['card_score']} (weight: 1x)")
    print(f"  Receipt score: {d2['receipt_score']} (weight: 2x)")
    print(f"  Combined: {d2['combined_score']}")
    print(f"  Verdict: {d2['verdict']}")
    print(f"  Basis: {d2['basis']}")
    print(f"  Track record: {proven.receipts.total_receipts} receipts, {proven.receipts.unique_orgs} witness orgs")
    
    print(f"\n--- .well-known/receipts.json ---")
    wk = proven.well_known_receipts()
    print(json.dumps(wk, indent=2))
    
    print(f"\n{'=' * 60}")
    print("THE MISSING CHAPTER")
    print(f"{'=' * 60}")
    print("""
  A2A Step 1: Coordinate          ✅ (Agent Card)
  A2A Step 2: Exchange caps       ✅ (Agent Card)  
  A2A Step 3: Trust the agent     ❌ → ✅ (L3.5 receipts)
  A2A Step 4: Verify after        ❌ → ✅ (Receipt chain)
  
  Agent Card says: "I can do X."
  Receipt chain says: "I did X, 47 times, witnessed by 5 orgs."
  
  Declaration + observation = trust.
  Declaration alone = hope.
""")


if __name__ == '__main__':
    demo()
