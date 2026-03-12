#!/usr/bin/env python3
"""
nversion-verifier.py — N-version programming for agent claim verification.

Avizienis 1985: multiple independent implementations verify the same claim.
Zheng et al 2025 (arXiv 2511.10400): LLM agents maintain BFT consensus at 85.7% fault rate.
claudecraft inspiration: 4+ agents independently verify Minecraft block state.

Each verifier independently checks a claim. Majority vote = verdict.
Byzantine tolerance: f < n/3 (classic) or f < n/2 (with LLM skepticism bonus).
"""

import hashlib
import random
from dataclasses import dataclass
from typing import Optional


@dataclass
class Claim:
    claim_id: str
    content: str
    scope_hash: str
    claimant: str


@dataclass
class Verification:
    verifier_id: str
    claim_id: str
    verdict: bool  # True = valid, False = invalid
    confidence: float  # 0.0-1.0
    evidence_hash: str
    is_byzantine: bool = False  # for simulation


class NVersionVerifier:
    def __init__(self, n_verifiers: int, byzantine_fraction: float = 0.0):
        self.n = n_verifiers
        self.byzantine_fraction = byzantine_fraction
        self.f_max_classic = (n_verifiers - 1) // 3  # classic BFT
        self.f_max_llm = (n_verifiers - 1) // 2  # with LLM skepticism (Zheng 2025)
    
    def verify_claim(self, claim: Claim, true_validity: bool) -> dict:
        """Simulate N independent verifications of a claim."""
        n_byzantine = int(self.n * self.byzantine_fraction)
        verifications = []
        
        for i in range(self.n):
            is_byz = i < n_byzantine
            if is_byz:
                # Byzantine: report opposite with high confidence
                verdict = not true_validity
                confidence = random.uniform(0.7, 0.95)
            else:
                # Honest: report correctly with variable confidence
                verdict = true_validity
                confidence = random.uniform(0.6, 0.99)
            
            evidence = f"{claim.claim_id}:{i}:{verdict}:{confidence}"
            v = Verification(
                verifier_id=f"verifier_{i}",
                claim_id=claim.claim_id,
                verdict=verdict,
                confidence=confidence,
                evidence_hash=hashlib.sha256(evidence.encode()).hexdigest()[:12],
                is_byzantine=is_byz
            )
            verifications.append(v)
        
        # Simple majority
        votes_true = sum(1 for v in verifications if v.verdict)
        votes_false = self.n - votes_true
        simple_majority = votes_true > votes_false
        
        # Confidence-weighted (CP-WBFT inspired)
        weighted_true = sum(v.confidence for v in verifications if v.verdict)
        weighted_false = sum(v.confidence for v in verifications if not v.verdict)
        weighted_majority = weighted_true > weighted_false
        
        # Quorum check
        honest_count = sum(1 for v in verifications if not v.is_byzantine)
        byzantine_count = self.n - honest_count
        classic_safe = byzantine_count <= self.f_max_classic
        llm_safe = byzantine_count <= self.f_max_llm
        
        correct_simple = simple_majority == true_validity
        correct_weighted = weighted_majority == true_validity
        
        grade = "A" if correct_weighted and classic_safe else \
                "B" if correct_weighted and llm_safe else \
                "C" if correct_weighted else \
                "F"
        
        return {
            "claim_id": claim.claim_id,
            "n_verifiers": self.n,
            "n_byzantine": byzantine_count,
            "byzantine_rate": f"{byzantine_count/self.n:.1%}",
            "true_validity": true_validity,
            "simple_majority": simple_majority,
            "weighted_majority": weighted_majority,
            "correct_simple": correct_simple,
            "correct_weighted": correct_weighted,
            "classic_bft_safe": classic_safe,
            "llm_bft_safe": llm_safe,
            "grade": grade,
            "votes": f"{votes_true}T/{votes_false}F",
            "weighted": f"{weighted_true:.2f}T/{weighted_false:.2f}F"
        }


def demo():
    print("=" * 65)
    print("N-VERSION VERIFIER — Independent Claim Verification")
    print("Avizienis 1985 + Zheng et al 2025 (CP-WBFT)")
    print("=" * 65)
    
    scenarios = [
        ("5 verifiers, 0% Byzantine", 5, 0.0, True),
        ("5 verifiers, 20% Byzantine", 5, 0.2, True),
        ("5 verifiers, 40% Byzantine", 5, 0.4, True),
        ("7 verifiers, 28% Byzantine (classic BFT limit)", 7, 0.28, True),
        ("7 verifiers, 57% Byzantine (above classic, below LLM)", 7, 0.57, False),
        ("9 verifiers, 33% Byzantine (classic limit)", 9, 0.33, True),
        ("9 verifiers, 85% Byzantine (Zheng 2025 extreme)", 9, 0.85, True),
    ]
    
    random.seed(42)
    
    for desc, n, byz, true_val in scenarios:
        claim = Claim(
            claim_id=f"claim_{n}_{int(byz*100)}",
            content="scope_hash matches observed state",
            scope_hash="abc123",
            claimant="agent_alpha"
        )
        
        verifier = NVersionVerifier(n, byz)
        result = verifier.verify_claim(claim, true_val)
        
        print(f"\n{'─' * 55}")
        print(f"Scenario: {desc}")
        print(f"  Verifiers: {result['n_verifiers']} | Byzantine: {result['n_byzantine']} ({result['byzantine_rate']})")
        print(f"  Votes: {result['votes']} | Weighted: {result['weighted']}")
        print(f"  Simple correct: {result['correct_simple']} | Weighted correct: {result['correct_weighted']}")
        print(f"  Classic BFT safe: {result['classic_bft_safe']} | LLM BFT safe: {result['llm_bft_safe']}")
        print(f"  Grade: {result['grade']}")
    
    print(f"\n{'=' * 65}")
    print("KEY INSIGHT: N-version = independent verification of same claim.")
    print("Classic BFT: f < n/3. LLM skepticism (Zheng 2025): f < n/2.")
    print("claudecraft's 4+ agent consensus IS N-version programming.")
    print("=" * 65)


if __name__ == "__main__":
    demo()
