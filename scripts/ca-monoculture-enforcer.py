#!/usr/bin/env python3
"""
ca-monoculture-enforcer.py — Enforce CA diversity at connection time.

Per santaclawd: "detection ≠ rejection — until enough counterparties blacklist,
the monoculture oracle still clears."

This is the enforcement layer: counterparties reject oracle verdicts
backed by monoculture CA BEFORE trusting the score. Like browsers
rejecting non-CT certs at the last mile.

Key insight: one large counterparty enforcing = enough to force adoption.
Chrome requiring CT forced the entire ecosystem. Same mechanism here.
"""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional
from collections import Counter


@dataclass
class OracleAttestation:
    oracle_id: str
    ca_fingerprint: str  # root CA that signed this oracle's cert
    operator: str
    model_family: str
    score: float
    evidence_grade: str  # A/B/C/D/F


@dataclass
class CADiversityPolicy:
    """Counterparty-side enforcement policy."""
    max_ca_concentration: float = 0.33  # max fraction sharing same CA
    min_unique_cas: int = 2             # minimum distinct CA roots
    reject_self_signed: bool = True
    require_ca_transparency: bool = False  # future: CA must be in public log
    
    def evaluate(self, attestations: list[OracleAttestation]) -> dict:
        n = len(attestations)
        if n == 0:
            return {"verdict": "NO_DATA", "accepted": [], "rejected": []}
        
        # Count CA fingerprints
        ca_counts = Counter(a.ca_fingerprint for a in attestations)
        unique_cas = len(ca_counts)
        max_ca = ca_counts.most_common(1)[0]
        max_ca_frac = max_ca[1] / n
        
        accepted = []
        rejected = []
        reasons = []
        
        # Check each attestation
        for att in attestations:
            att_reasons = []
            
            # Self-signed check
            if self.reject_self_signed and att.ca_fingerprint == f"self:{att.oracle_id}":
                att_reasons.append("SELF_SIGNED")
            
            # CA concentration: reject if this CA is over-represented
            ca_frac = ca_counts[att.ca_fingerprint] / n
            if ca_frac > self.max_ca_concentration:
                att_reasons.append(f"CA_MONOCULTURE({att.ca_fingerprint[:8]}={ca_frac:.0%})")
            
            if att_reasons:
                rejected.append({"oracle": att.oracle_id, "reasons": att_reasons, "score": att.score})
            else:
                accepted.append({"oracle": att.oracle_id, "score": att.score, "ca": att.ca_fingerprint[:12]})
        
        # Global checks
        if unique_cas < self.min_unique_cas and n >= self.min_unique_cas:
            reasons.append(f"INSUFFICIENT_CA_DIVERSITY({unique_cas}<{self.min_unique_cas})")
        
        # Compute filtered score (only accepted attestations)
        if accepted:
            filtered_score = sum(a["score"] for a in accepted) / len(accepted)
        else:
            filtered_score = 0.0
        
        # Unfiltered score (all)
        raw_score = sum(a.score for a in attestations) / n
        
        # Verdict
        if not accepted:
            verdict = "ALL_REJECTED"
        elif len(rejected) > n / 2:
            verdict = "MAJORITY_REJECTED"
        elif rejected:
            verdict = "PARTIAL_REJECT"
        elif reasons:
            verdict = "WARNING"
        else:
            verdict = "CLEAN"
        
        return {
            "verdict": verdict,
            "raw_score": round(raw_score, 3),
            "filtered_score": round(filtered_score, 3),
            "score_delta": round(raw_score - filtered_score, 3),
            "accepted": len(accepted),
            "rejected": len(rejected),
            "unique_cas": unique_cas,
            "max_ca_concentration": round(max_ca_frac, 2),
            "global_warnings": reasons,
            "accepted_detail": accepted,
            "rejected_detail": rejected,
        }


def demo():
    policy = CADiversityPolicy()
    
    # Scenario 1: Diverse CAs — all accepted
    diverse = [
        OracleAttestation("o1", "ca:letsencrypt", "acme", "claude", 0.92, "A"),
        OracleAttestation("o2", "ca:digicert", "beta", "gpt4", 0.88, "B"),
        OracleAttestation("o3", "ca:comodo", "gamma", "gemini", 0.85, "B"),
        OracleAttestation("o4", "ca:globalsign", "delta", "llama", 0.90, "A"),
        OracleAttestation("o5", "ca:sectigo", "epsilon", "mistral", 0.87, "B"),
    ]
    
    # Scenario 2: CA monoculture — 4/5 same CA
    monoculture = [
        OracleAttestation("o1", "ca:internal_corp", "acme", "claude", 0.95, "A"),
        OracleAttestation("o2", "ca:internal_corp", "beta", "gpt4", 0.93, "A"),
        OracleAttestation("o3", "ca:internal_corp", "gamma", "gemini", 0.91, "B"),
        OracleAttestation("o4", "ca:internal_corp", "delta", "llama", 0.94, "A"),
        OracleAttestation("o5", "ca:digicert", "epsilon", "mistral", 0.72, "C"),
    ]
    
    # Scenario 3: Sybil with high scores via self-signed
    sybil = [
        OracleAttestation("s1", "self:s1", "sybil_corp", "claude", 0.99, "A"),
        OracleAttestation("s2", "self:s2", "sybil_corp", "claude", 0.98, "A"),
        OracleAttestation("s3", "self:s3", "sybil_corp", "claude", 0.97, "A"),
    ]
    
    for name, attestations in [("diverse_cas", diverse), ("ca_monoculture", monoculture), ("sybil_self_signed", sybil)]:
        result = policy.evaluate(attestations)
        print(f"\n{'='*55}")
        print(f"Scenario: {name}")
        print(f"Verdict: {result['verdict']}")
        print(f"Raw score: {result['raw_score']} → Filtered: {result['filtered_score']} (delta: {result['score_delta']})")
        print(f"Accepted: {result['accepted']}/{result['accepted']+result['rejected']} | Unique CAs: {result['unique_cas']}")
        if result['rejected_detail']:
            for r in result['rejected_detail']:
                print(f"  REJECTED: {r['oracle']} (score={r['score']}) — {', '.join(r['reasons'])}")
        if result['global_warnings']:
            print(f"  WARNINGS: {result['global_warnings']}")


if __name__ == "__main__":
    demo()
