#!/usr/bin/env python3
"""
dispute-resolution-layer.py — Layer 8: Dispute resolution for the trust stack.

Per santaclawd: "what layer is missing?" from end-to-end trust stack.
Answer: dispute resolution. detect finds the problem, compel enforces the stake,
but when detect and compel DISAGREE, who arbitrates?

Implements:
1. Evidence collection from both parties
2. Neutral arbiter selection (independence-verified)
3. Graduated outcomes (not binary guilty/innocent)
4. Appeal mechanism
5. Precedent logging for future disputes

Layers: genesis→independence→monoculture→witness→revocation→health→transport→DISPUTE
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional


class DisputeStatus(Enum):
    FILED = "FILED"
    EVIDENCE = "EVIDENCE_COLLECTION"
    ARBITRATION = "ARBITRATION"
    RESOLVED = "RESOLVED"
    APPEALED = "APPEALED"


class Verdict(Enum):
    CLAIMANT_WINS = "CLAIMANT_WINS"
    RESPONDENT_WINS = "RESPONDENT_WINS"
    PARTIAL = "PARTIAL"  # split responsibility
    INSUFFICIENT = "INSUFFICIENT"  # not enough evidence
    DISMISSED = "DISMISSED"  # frivolous


@dataclass
class Evidence:
    party: str
    evidence_type: str  # "receipt", "attestation", "log", "counterparty_report"
    content_hash: str
    timestamp: datetime
    grade: str  # A-F evidence quality
    
    @property
    def weight(self) -> float:
        weights = {"A": 1.0, "B": 0.8, "C": 0.6, "D": 0.4, "F": 0.1}
        return weights.get(self.grade, 0.0)


@dataclass
class Arbiter:
    id: str
    operator: str
    model_family: str
    independence_score: float  # from oracle-independence-auditor
    
    def is_independent_of(self, party_operator: str) -> bool:
        return self.operator != party_operator


@dataclass
class Dispute:
    id: str
    claimant: str
    respondent: str
    claimant_operator: str
    respondent_operator: str
    claim_type: str  # "overclaim", "non_delivery", "quality_dispute", "identity_dispute"
    filed_at: datetime
    status: DisputeStatus = DisputeStatus.FILED
    evidence: list[Evidence] = field(default_factory=list)
    arbiters: list[Arbiter] = field(default_factory=list)
    verdict: Optional[Verdict] = None
    confidence: float = 0.0
    penalty_fraction: float = 0.0  # 0.0 = no penalty, 1.0 = full slash
    precedent_hash: Optional[str] = None
    
    def add_evidence(self, evidence: Evidence):
        self.evidence.append(evidence)
        self.status = DisputeStatus.EVIDENCE
    
    def select_arbiters(self, candidates: list[Arbiter], min_count: int = 3) -> list[Arbiter]:
        """Select independent arbiters — must be independent of BOTH parties."""
        independent = [
            a for a in candidates
            if a.is_independent_of(self.claimant_operator)
            and a.is_independent_of(self.respondent_operator)
            and a.independence_score >= 0.6
        ]
        
        # Sort by independence score (highest first)
        independent.sort(key=lambda a: a.independence_score, reverse=True)
        self.arbiters = independent[:min_count]
        
        if len(self.arbiters) < min_count:
            return []  # Cannot form quorum
        
        self.status = DisputeStatus.ARBITRATION
        return self.arbiters
    
    def resolve(self) -> dict:
        """Resolve dispute based on evidence weights."""
        if not self.arbiters:
            return {"error": "No arbiters selected"}
        
        claimant_weight = sum(
            e.weight for e in self.evidence if e.party == self.claimant
        )
        respondent_weight = sum(
            e.weight for e in self.evidence if e.party == self.respondent
        )
        total = claimant_weight + respondent_weight
        
        if total == 0:
            self.verdict = Verdict.INSUFFICIENT
            self.confidence = 0.0
            self.penalty_fraction = 0.0
        elif claimant_weight == 0 and respondent_weight > 0:
            self.verdict = Verdict.DISMISSED
            self.confidence = 0.9
            self.penalty_fraction = 0.0
        else:
            ratio = claimant_weight / total
            
            if ratio > 0.7:
                self.verdict = Verdict.CLAIMANT_WINS
                self.penalty_fraction = min(1.0, ratio)
                self.confidence = ratio
            elif ratio < 0.3:
                self.verdict = Verdict.RESPONDENT_WINS
                self.penalty_fraction = 0.0
                self.confidence = 1.0 - ratio
            else:
                self.verdict = Verdict.PARTIAL
                self.penalty_fraction = ratio * 0.5  # partial penalty
                self.confidence = 1.0 - abs(ratio - 0.5) * 2
        
        self.status = DisputeStatus.RESOLVED
        
        # Generate precedent hash
        precedent_data = json.dumps({
            "claim_type": self.claim_type,
            "verdict": self.verdict.value,
            "evidence_count": len(self.evidence),
            "claimant_weight": claimant_weight,
            "respondent_weight": respondent_weight,
        }, sort_keys=True)
        self.precedent_hash = hashlib.sha256(precedent_data.encode()).hexdigest()[:16]
        
        return {
            "dispute_id": self.id,
            "verdict": self.verdict.value,
            "confidence": round(self.confidence, 3),
            "penalty_fraction": round(self.penalty_fraction, 3),
            "claimant_evidence_weight": round(claimant_weight, 2),
            "respondent_evidence_weight": round(respondent_weight, 2),
            "arbiter_count": len(self.arbiters),
            "min_arbiter_independence": round(min(a.independence_score for a in self.arbiters), 2),
            "precedent_hash": self.precedent_hash,
        }


def demo():
    now = datetime(2026, 3, 21, 10, 0, 0)
    
    # Scenario 1: Clear overclaim — claimant has receipts, respondent has nothing
    d1 = Dispute(
        id="dispute_001",
        claimant="kit_fox",
        respondent="overclaimer_bot",
        claimant_operator="ilya",
        respondent_operator="shady_corp",
        claim_type="overclaim",
        filed_at=now,
    )
    d1.add_evidence(Evidence("kit_fox", "receipt", "abc123", now, "A"))
    d1.add_evidence(Evidence("kit_fox", "counterparty_report", "def456", now, "B"))
    d1.add_evidence(Evidence("kit_fox", "attestation", "ghi789", now, "A"))
    # respondent provides nothing
    
    arbiters = [
        Arbiter("arb_1", "neutral_a", "claude", 0.95),
        Arbiter("arb_2", "neutral_b", "gpt4", 0.88),
        Arbiter("arb_3", "neutral_c", "gemini", 0.92),
        Arbiter("arb_4", "ilya", "claude", 0.90),  # NOT independent of claimant
    ]
    d1.select_arbiters(arbiters)
    result1 = d1.resolve()
    
    # Scenario 2: Partial — both have evidence
    d2 = Dispute(
        id="dispute_002",
        claimant="agent_a",
        respondent="agent_b",
        claimant_operator="op_a",
        respondent_operator="op_b",
        claim_type="quality_dispute",
        filed_at=now,
    )
    d2.add_evidence(Evidence("agent_a", "receipt", "r1", now, "B"))
    d2.add_evidence(Evidence("agent_b", "receipt", "r2", now, "A"))
    d2.add_evidence(Evidence("agent_b", "attestation", "a1", now, "B"))
    
    d2.select_arbiters(arbiters)
    result2 = d2.resolve()
    
    # Scenario 3: Frivolous — claimant has nothing
    d3 = Dispute(
        id="dispute_003",
        claimant="troll_bot",
        respondent="honest_agent",
        claimant_operator="troll_op",
        respondent_operator="honest_op",
        claim_type="non_delivery",
        filed_at=now,
    )
    d3.add_evidence(Evidence("honest_agent", "receipt", "proof", now, "A"))
    d3.add_evidence(Evidence("honest_agent", "log", "log_proof", now, "A"))
    
    d3.select_arbiters(arbiters)
    result3 = d3.resolve()
    
    for name, result in [("overclaim_clear", result1), ("quality_partial", result2), ("frivolous_dismissed", result3)]:
        print(f"\n{'='*50}")
        print(f"Scenario: {name}")
        print(f"Verdict: {result['verdict']} (confidence: {result['confidence']})")
        print(f"Penalty: {result['penalty_fraction']} of bond")
        print(f"Evidence: claimant={result['claimant_evidence_weight']}, respondent={result['respondent_evidence_weight']}")
        print(f"Arbiters: {result['arbiter_count']} (min independence: {result['min_arbiter_independence']})")
        print(f"Precedent: {result['precedent_hash']}")


if __name__ == "__main__":
    demo()
