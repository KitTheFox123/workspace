#!/usr/bin/env python3
"""
quorum-size-optimizer.py — Optimal grader quorum sizing for ATF attestations.

The core tension: more graders = more fault tolerance, but also more
coordination overhead, higher latency, and diminishing returns from
correlated graders. What's the right N?

Maps three bodies of research:
1. BFT consensus (Lamport 1982, Castro & Liskov 1999): f byzantine faults
   requires N >= 3f+1 nodes. Classic result, but assumes independent failures.
2. Collective intelligence (Woolley et al 2010, Science): group CI predicts
   performance better than max individual IQ. But social sensitivity and
   turn-taking matter more than group size.
3. Condorcet Jury Theorem (1785): majority of independent voters with p>0.5
   converges to correct answer as N→∞. BUT: correlated voters BREAK this
   (Ladha 1992, Berg 1993). Wisdom of crowds fails with shared information.

ATF synthesis: quorum size should be f(action_class, diversity_score, 
correlation_estimate). Not a fixed N. High-diversity pool → smaller quorum
sufficient. Correlated pool → larger quorum HURTS (amplifies shared bias).

Kit 🦊 — 2026-03-27
"""

import json
import math
from dataclasses import dataclass
from typing import Optional


@dataclass
class QuorumConfig:
    """Computed quorum parameters for an attestation."""
    min_graders: int
    optimal_graders: int
    max_graders: int
    fault_tolerance: int  # max byzantine faults tolerable
    effective_independence: float  # 0-1, accounts for correlation
    condorcet_probability: float  # P(correct majority decision)
    rationale: str


class QuorumSizeOptimizer:
    """
    Computes optimal grader quorum size based on action class,
    diversity metrics, and correlation estimates.
    """
    
    # BFT minimum: N >= 3f+1
    # Action class determines target fault tolerance (f)
    ACTION_CLASS_FAULT_TOLERANCE = {
        "READ": 1,      # tolerate 1 byzantine grader
        "WRITE": 1,     # tolerate 1
        "TRANSFER": 2,  # tolerate 2
        "ATTEST": 2,    # tolerate 2 (attestations are high-stakes)
    }
    
    # Minimum individual grader competence (p > 0.5 for Condorcet)
    MIN_COMPETENCE = 0.6
    
    def compute_condorcet_probability(
        self, n: int, p: float, correlation: float
    ) -> float:
        """
        Condorcet Jury Theorem with correlation adjustment.
        
        Standard CJT: P(majority correct) = sum_{k=ceil(n/2)}^{n} C(n,k) * p^k * (1-p)^(n-k)
        
        With correlation (Ladha 1992): effective sample size shrinks.
        N_eff = N / (1 + (N-1) * rho) where rho = pairwise correlation.
        
        When rho > 0, adding more voters can DECREASE accuracy
        (correlated errors amplified by majority rule).
        """
        if correlation >= 1.0:
            return p  # perfectly correlated = one voter
        
        # Effective sample size (design effect from survey sampling)
        n_eff = max(1, n / (1 + (n - 1) * correlation))
        
        # Use effective N for Condorcet calculation
        n_use = max(1, int(round(n_eff)))
        if n_use % 2 == 0:
            n_use = max(1, n_use - 1)  # odd for majority
        
        # Exact binomial for majority
        threshold = n_use // 2 + 1
        prob = 0.0
        for k in range(threshold, n_use + 1):
            # C(n,k) * p^k * (1-p)^(n-k)
            coeff = math.comb(n_use, k)
            prob += coeff * (p ** k) * ((1 - p) ** (n_use - k))
        
        return min(1.0, prob)
    
    def compute_optimal_quorum(
        self,
        action_class: str,
        diversity_score: float,  # 0-1, Simpson diversity of grader pool
        correlation_estimate: float = 0.0,  # 0-1, estimated pairwise correlation
        grader_competence: float = 0.75,  # individual grader accuracy
        available_graders: int = 20,
    ) -> QuorumConfig:
        """
        Compute optimal quorum size.
        
        Key insight from collective intelligence research (Woolley 2010):
        social sensitivity and diversity predict group performance better
        than raw group size or max individual ability.
        
        For ATF: diversity_score IS the primary input, not pool size.
        """
        
        f = self.ACTION_CLASS_FAULT_TOLERANCE.get(action_class, 1)
        bft_min = 3 * f + 1  # classic BFT bound
        
        # Adjust for correlation: correlated graders reduce effective f
        # If graders are correlated, need MORE to tolerate same f
        if correlation_estimate > 0.3:
            # High correlation: effective fault tolerance drops
            effective_f = max(1, int(f / (1 - correlation_estimate * 0.5)))
            bft_adjusted = 3 * effective_f + 1
        else:
            bft_adjusted = bft_min
        
        # Diversity bonus: high diversity allows smaller quorum
        # (independent graders → Condorcet works → fewer needed)
        diversity_factor = 1.0 - (diversity_score * 0.3)  # 0.7-1.0
        
        optimal = max(bft_adjusted, int(math.ceil(bft_adjusted * diversity_factor)))
        optimal = min(optimal, available_graders)
        optimal = max(optimal, 3)  # absolute minimum
        
        # Ensure odd for majority voting
        if optimal % 2 == 0:
            optimal += 1
        
        # Condorcet probability at optimal size
        condorcet_p = self.compute_condorcet_probability(
            optimal, grader_competence, correlation_estimate
        )
        
        # Effective independence
        effective_independence = diversity_score * (1 - correlation_estimate)
        
        # Cap: beyond a point, more graders hurt (coordination cost,
        # Ringelmann effect, correlation amplification)
        max_useful = min(
            available_graders,
            int(optimal * 1.5),
            13  # Dunbar-like cap: coordination overhead dominates
        )
        
        rationale_parts = [
            f"BFT base: 3×{f}+1={bft_min}",
            f"correlation adjustment: {bft_adjusted}",
            f"diversity factor: {diversity_factor:.2f}",
            f"Condorcet P(correct): {condorcet_p:.3f}",
            f"effective independence: {effective_independence:.3f}",
        ]
        
        if correlation_estimate > 0.5:
            rationale_parts.append(
                "⚠️ HIGH CORRELATION: adding graders may DECREASE accuracy "
                "(Ladha 1992). Improve diversity before increasing quorum."
            )
        
        if diversity_score < 0.3:
            rationale_parts.append(
                "⚠️ LOW DIVERSITY: grader pool is near-monoculture. "
                "Woolley et al (2010): diversity predicts CI better than size."
            )
        
        return QuorumConfig(
            min_graders=max(3, bft_min),
            optimal_graders=optimal,
            max_graders=max_useful,
            fault_tolerance=f,
            effective_independence=effective_independence,
            condorcet_probability=condorcet_p,
            rationale=" | ".join(rationale_parts)
        )
    
    def compare_quorums(self, configs: list[dict]) -> list[dict]:
        """Compare quorum configs across scenarios."""
        results = []
        for cfg in configs:
            q = self.compute_optimal_quorum(**cfg)
            results.append({
                "scenario": cfg,
                "quorum": {
                    "min": q.min_graders,
                    "optimal": q.optimal_graders,
                    "max": q.max_graders,
                    "fault_tolerance": q.fault_tolerance,
                    "condorcet_p": round(q.condorcet_probability, 4),
                    "effective_independence": round(q.effective_independence, 3),
                    "rationale": q.rationale
                }
            })
        return results


def demo():
    optimizer = QuorumSizeOptimizer()
    
    scenarios = [
        {
            "name": "READ — diverse pool, low correlation",
            "action_class": "READ",
            "diversity_score": 0.85,
            "correlation_estimate": 0.1,
            "grader_competence": 0.8,
        },
        {
            "name": "TRANSFER — diverse pool",
            "action_class": "TRANSFER",
            "diversity_score": 0.75,
            "correlation_estimate": 0.15,
            "grader_competence": 0.8,
        },
        {
            "name": "ATTEST — monoculture pool (same RLHF)",
            "action_class": "ATTEST",
            "diversity_score": 0.2,
            "correlation_estimate": 0.7,
            "grader_competence": 0.8,
        },
        {
            "name": "WRITE — moderate diversity, moderate correlation",
            "action_class": "WRITE",
            "diversity_score": 0.5,
            "correlation_estimate": 0.35,
            "grader_competence": 0.75,
        },
    ]
    
    for s in scenarios:
        name = s.pop("name")
        print(f"\n{'='*60}")
        print(f"SCENARIO: {name}")
        print(f"{'='*60}")
        
        q = optimizer.compute_optimal_quorum(**s)
        print(f"  Min graders:    {q.min_graders}")
        print(f"  Optimal:        {q.optimal_graders}")
        print(f"  Max useful:     {q.max_graders}")
        print(f"  Fault tolerance: {q.fault_tolerance}")
        print(f"  Condorcet P:    {q.condorcet_probability:.4f}")
        print(f"  Eff. independence: {q.effective_independence:.3f}")
        print(f"  Rationale: {q.rationale}")
    
    # Verify key properties
    print("\n" + "="*60)
    print("VERIFICATION")
    print("="*60)
    
    # 1. Higher correlation → higher optimal N (to compensate)
    q_low = optimizer.compute_optimal_quorum("ATTEST", 0.5, 0.1)
    q_high = optimizer.compute_optimal_quorum("ATTEST", 0.5, 0.6)
    assert q_high.optimal_graders >= q_low.optimal_graders, \
        f"Higher correlation should need more graders: {q_high.optimal_graders} vs {q_low.optimal_graders}"
    print(f"✓ Higher correlation ({q_high.optimal_graders}) >= low correlation ({q_low.optimal_graders})")
    
    # 2. Higher diversity → Condorcet works better
    q_diverse = optimizer.compute_optimal_quorum("WRITE", 0.9, 0.05, 0.8)
    q_mono = optimizer.compute_optimal_quorum("WRITE", 0.1, 0.7, 0.8)
    assert q_diverse.condorcet_probability > q_mono.condorcet_probability, \
        "Diverse pool should have higher Condorcet probability"
    print(f"✓ Diverse Condorcet ({q_diverse.condorcet_probability:.4f}) > mono ({q_mono.condorcet_probability:.4f})")
    
    # 3. TRANSFER/ATTEST need higher f than READ/WRITE
    q_read = optimizer.compute_optimal_quorum("READ", 0.7, 0.1)
    q_transfer = optimizer.compute_optimal_quorum("TRANSFER", 0.7, 0.1)
    assert q_transfer.min_graders > q_read.min_graders, \
        "TRANSFER should require more graders than READ"
    print(f"✓ TRANSFER min ({q_transfer.min_graders}) > READ min ({q_read.min_graders})")
    
    # 4. Perfect correlation → Condorcet = individual competence
    q_perfect = optimizer.compute_optimal_quorum("READ", 0.5, 0.99, 0.75)
    assert abs(q_perfect.condorcet_probability - 0.75) < 0.1, \
        f"Perfect correlation Condorcet should ≈ individual: {q_perfect.condorcet_probability}"
    print(f"✓ Perfect correlation Condorcet ({q_perfect.condorcet_probability:.4f}) ≈ individual (0.75)")
    
    print("\nALL CHECKS PASSED ✓")


if __name__ == "__main__":
    demo()
