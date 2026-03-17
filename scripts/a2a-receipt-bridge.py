#!/usr/bin/env python3
"""
a2a-receipt-bridge.py — Bridge Google A2A Agent Cards with L3.5 trust receipts.

A2A solves coordination (steps 1-2). It does NOT solve identity verification (step 3).
Agent Cards declare capability. Receipts PROVE history.

This bridge:
1. Takes an A2A Agent Card (self-declared)
2. Looks up L3.5 receipts for that agent (independently verified)
3. Returns an enriched card with trust evidence

"A resume vs a background check" (Kit, 2026-03-17)

Per santaclawd: "the infrastructure that ships step 3 wins."

Usage:
    python3 a2a-receipt-bridge.py [--demo]
"""

import json
import hashlib
from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class A2AAgentCard:
    """Google A2A Agent Card — self-declared capability."""
    name: str
    description: str
    url: str
    capabilities: List[str] = field(default_factory=list)
    skills: List[Dict] = field(default_factory=list)
    # A2A spec fields
    version: str = "1.0"
    protocol: str = "a2a"
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "url": self.url,
            "capabilities": self.capabilities,
            "skills": self.skills,
            "version": self.version,
            "protocol": self.protocol,
        }


@dataclass
class ReceiptSummary:
    """L3.5 receipt history — independently verified."""
    agent_id: str
    total_receipts: int = 0
    deliveries: int = 0
    refusals: int = 0
    slashes: int = 0
    avg_dimensions: Dict[str, float] = field(default_factory=dict)
    unique_witnesses: int = 0
    unique_orgs: int = 0
    oldest_receipt: str = ""
    newest_receipt: str = ""
    has_scars: bool = False
    
    def trust_grade(self) -> str:
        """Simple grade based on evidence quality."""
        if self.total_receipts == 0:
            return "U"  # Unverified
        if self.total_receipts < 3:
            return "D"  # Insufficient history
        
        avg_score = sum(self.avg_dimensions.values()) / max(len(self.avg_dimensions), 1)
        diversity = self.unique_orgs / max(self.unique_witnesses, 1)
        has_refusals = self.refusals > 0  # Costly signal bonus
        
        score = avg_score * 0.4 + diversity * 0.3 + (0.1 if has_refusals else 0) + min(self.total_receipts / 50, 0.2)
        
        if score > 0.75: return "A"
        if score > 0.55: return "B"
        if score > 0.35: return "C"
        return "D"


def enrich_agent_card(card: A2AAgentCard, receipts: ReceiptSummary) -> Dict:
    """Bridge A2A Agent Card with L3.5 receipt evidence."""
    enriched = card.to_dict()
    
    # Add L3.5 trust extension
    enriched["x-l35-trust"] = {
        "evidence_available": receipts.total_receipts > 0,
        "receipt_count": receipts.total_receipts,
        "trust_grade": receipts.trust_grade(),
        "dimensions": receipts.avg_dimensions,
        "witness_diversity": {
            "unique_witnesses": receipts.unique_witnesses,
            "unique_orgs": receipts.unique_orgs,
            "diversity_ratio": round(receipts.unique_orgs / max(receipts.unique_witnesses, 1), 3),
        },
        "history": {
            "deliveries": receipts.deliveries,
            "refusals": receipts.refusals,
            "slashes": receipts.slashes,
            "has_scars": receipts.has_scars,
            "oldest": receipts.oldest_receipt,
            "newest": receipts.newest_receipt,
        },
        "verification": "independent",  # NOT self-declared
        "spec_version": "receipt-format-minimal-0.2.0",
    }
    
    # Trust decision helpers
    grade = receipts.trust_grade()
    enriched["x-l35-advisory"] = {
        "U": "UNVERIFIED: No receipt history. Treat as unknown. High escrow recommended.",
        "D": "INSUFFICIENT: Too few receipts for confidence. Proceed with caution.",
        "C": "DEVELOPING: Some history, moderate confidence. Standard terms.",
        "B": "ESTABLISHED: Good history, diverse witnesses. Reduced escrow eligible.",
        "A": "TRUSTED: Strong history, independent attestation, principled refusals. Preferred terms.",
    }.get(grade, "UNKNOWN")
    
    return enriched


def demo():
    print("=" * 60)
    print("A2A ↔ L3.5 RECEIPT BRIDGE")
    print("Agent Cards declare. Receipts prove.")
    print("=" * 60)
    
    # Agent with good A2A card but NO receipts
    card_unverified = A2AAgentCard(
        name="flashy-agent",
        description="Ultra-fast delivery agent. 99.9% success rate. Trust me.",
        url="https://flashy.agent/a2a",
        capabilities=["delivery", "research", "translation"],
        skills=[{"name": "web_search", "description": "Search the web"}],
    )
    receipts_none = ReceiptSummary(agent_id="agent:flashy")
    
    enriched_none = enrich_agent_card(card_unverified, receipts_none)
    
    print(f"\n--- AGENT: {card_unverified.name} ---")
    print(f"Self-declared: \"{card_unverified.description}\"")
    print(f"A2A capabilities: {card_unverified.capabilities}")
    print(f"L3.5 grade: {enriched_none['x-l35-trust']['trust_grade']}")
    print(f"Advisory: {enriched_none['x-l35-advisory']}")
    print(f"Receipts: {enriched_none['x-l35-trust']['receipt_count']}")
    
    # Agent with modest card but STRONG receipts
    card_proven = A2AAgentCard(
        name="kit_fox",
        description="Research and delivery agent.",
        url="https://kit.fox/a2a",
        capabilities=["research", "delivery"],
    )
    receipts_strong = ReceiptSummary(
        agent_id="agent:kit_fox",
        total_receipts=47,
        deliveries=42,
        refusals=3,  # Costly signal!
        slashes=2,
        avg_dimensions={"T": 0.89, "G": 0.82, "A": 0.91, "S": 0.76, "C": 0.88},
        unique_witnesses=12,
        unique_orgs=8,
        oldest_receipt="2026-02-14T00:00:00Z",
        newest_receipt="2026-03-17T19:00:00Z",
        has_scars=True,
    )
    
    enriched_strong = enrich_agent_card(card_proven, receipts_strong)
    
    print(f"\n--- AGENT: {card_proven.name} ---")
    print(f"Self-declared: \"{card_proven.description}\"")
    print(f"A2A capabilities: {card_proven.capabilities}")
    print(f"L3.5 grade: {enriched_strong['x-l35-trust']['trust_grade']}")
    print(f"Advisory: {enriched_strong['x-l35-advisory']}")
    print(f"Receipts: {enriched_strong['x-l35-trust']['receipt_count']}")
    print(f"Witness orgs: {enriched_strong['x-l35-trust']['witness_diversity']['unique_orgs']}")
    print(f"Has refusals: {enriched_strong['x-l35-trust']['history']['refusals']} (costly signal)")
    print(f"Has scars: {enriched_strong['x-l35-trust']['history']['has_scars']} (recovered from slash)")
    
    # The point
    print(f"\n{'=' * 60}")
    print("THE MISSING CHAPTER")
    print(f"{'=' * 60}")
    print(f"\n  A2A Step 1: Coordinate          ✅ (spec covers this)")
    print(f"  A2A Step 2: Exchange Cards       ✅ (spec covers this)")
    print(f"  A2A Step 3: Trust the agent      ❓ (NO ANSWER IN SPEC)")
    print(f"  A2A Step 4: Verify history       ❓ (NO ANSWER IN SPEC)")
    print(f"\n  L3.5 receipts = Steps 3 & 4.")
    print(f"  Ship as A2A extension (x-l35-trust), not competing protocol.")
    print(f"  Complement, not compete.")
    print(f"\n  flashy-agent: great card, zero receipts → UNVERIFIED")
    print(f"  kit_fox: modest card, 47 receipts → TRUSTED")
    print(f"\n  The resume said 99.9%. The background check said 0 history.")
    print(f"  Evidence > claims. Always.")


if __name__ == "__main__":
    demo()
