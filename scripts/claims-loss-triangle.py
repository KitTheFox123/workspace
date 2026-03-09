#!/usr/bin/env python3
"""claims-loss-triangle.py — Actuarial loss triangle for attestation claims.

Tracks attestation outcomes over development periods to build loss triangles,
calculate IBNR (Incurred But Not Reported) reserves, and price attestation
insurance premiums actuarially.

Santaclawd's insight: "no claims data = no actuarial pricing = moral hazard wins."
Insurance solved this in 1934 with loss development triangles.

Usage:
    python3 claims-loss-triangle.py [--demo]
"""

import argparse
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional


@dataclass 
class Claim:
    """An attestation outcome claim."""
    attestor_id: str
    agent_id: str
    period: int  # Origin period (e.g., month)
    development: int  # Development lag (periods since origin)
    attested_score: float  # What attestor said
    actual_outcome: float  # What actually happened (0=failure, 1=success)
    loss: float  # abs(attested - actual)


@dataclass
class LossTriangle:
    """Actuarial loss development triangle for attestation claims."""
    claims: List[Claim] = field(default_factory=list)
    
    def add_claim(self, claim: Claim):
        self.claims.append(claim)
    
    def build_triangle(self, max_period: int = 6, max_dev: int = 4) -> List[List[Optional[float]]]:
        """Build cumulative loss triangle."""
        triangle = [[None] * (max_dev + 1) for _ in range(max_period + 1)]
        
        for p in range(max_period + 1):
            for d in range(max_dev + 1):
                matching = [c for c in self.claims if c.period == p and c.development <= d]
                if matching:
                    triangle[p][d] = sum(c.loss for c in matching) / len(matching)
        
        return triangle
    
    def development_factors(self, triangle: List[List[Optional[float]]]) -> List[Optional[float]]:
        """Calculate link ratios (development factors) from triangle."""
        factors = []
        max_dev = len(triangle[0]) - 1
        
        for d in range(max_dev):
            num_sum = 0.0
            den_sum = 0.0
            for p in range(len(triangle)):
                if triangle[p][d] is not None and triangle[p][d + 1] is not None:
                    if triangle[p][d] > 0:
                        den_sum += triangle[p][d]
                        num_sum += triangle[p][d + 1]
            
            if den_sum > 0:
                factors.append(num_sum / den_sum)
            else:
                factors.append(None)
        
        return factors
    
    def estimate_ibnr(self, triangle: List[List[Optional[float]]], 
                       factors: List[Optional[float]]) -> Dict[int, float]:
        """Estimate IBNR reserves per origin period."""
        ibnr = {}
        
        for p in range(len(triangle)):
            # Find latest known development
            latest_d = None
            latest_val = None
            for d in range(len(triangle[p])):
                if triangle[p][d] is not None:
                    latest_d = d
                    latest_val = triangle[p][d]
            
            if latest_d is not None and latest_val is not None:
                # Project to ultimate using remaining factors
                projected = latest_val
                for d in range(latest_d, len(factors)):
                    if factors[d] is not None:
                        projected *= factors[d]
                
                ibnr[p] = max(0, projected - latest_val)
        
        return ibnr
    
    def attestor_brier(self) -> Dict[str, float]:
        """Brier scores per attestor from claims history."""
        scores: Dict[str, List[float]] = {}
        for c in self.claims:
            if c.attestor_id not in scores:
                scores[c.attestor_id] = []
            scores[c.attestor_id].append((c.attested_score - c.actual_outcome) ** 2)
        
        return {a: sum(s) / len(s) for a, s in scores.items()}
    
    def price_premium(self, attestor_id: str, base_rate: float = 0.05) -> float:
        """Actuarial premium pricing based on claims history."""
        brier = self.attestor_brier()
        if attestor_id not in brier:
            return base_rate * 2.0  # New attestor = max premium
        
        score = brier[attestor_id]
        # Better Brier → lower premium
        multiplier = 1.0 + (score * 10)  # Scale: 0.0 Brier = 1x, 0.25 = 3.5x
        return base_rate * multiplier
    
    def grade(self) -> str:
        """Grade claims database completeness."""
        if len(self.claims) == 0:
            return "F"
        
        periods = set(c.period for c in self.claims)
        attestors = set(c.attestor_id for c in self.claims)
        outcomes = sum(1 for c in self.claims if c.actual_outcome is not None)
        
        score = 0
        if len(self.claims) >= 50: score += 25
        elif len(self.claims) >= 20: score += 15
        elif len(self.claims) >= 5: score += 5
        
        if len(periods) >= 4: score += 25
        elif len(periods) >= 2: score += 15
        
        if len(attestors) >= 3: score += 25
        elif len(attestors) >= 2: score += 15
        
        if outcomes / len(self.claims) > 0.8: score += 25
        elif outcomes / len(self.claims) > 0.5: score += 15
        
        if score >= 80: return "A"
        if score >= 60: return "B"
        if score >= 40: return "C"
        if score >= 20: return "D"
        return "F"


def demo():
    """Demo with synthetic claims data."""
    lt = LossTriangle()
    
    import random
    random.seed(42)
    
    # Simulate 3 attestors over 6 periods
    attestors = {
        "calibrated_alice": 0.05,   # Low Brier (good)
        "rubber_stamp_bob": 0.35,   # High Brier (bad) 
        "new_carol": 0.15,          # Medium Brier
    }
    
    for period in range(6):
        for attestor, noise in attestors.items():
            for dev in range(min(period + 1, 4)):
                actual = random.choice([0.0, 0.0, 1.0, 1.0, 1.0])  # 60% success
                attested = min(1.0, max(0.0, actual + random.gauss(0, noise)))
                lt.add_claim(Claim(
                    attestor_id=attestor,
                    agent_id=f"agent_{period}",
                    period=period,
                    development=dev,
                    attested_score=round(attested, 3),
                    actual_outcome=actual,
                    loss=round(abs(attested - actual), 3)
                ))
    
    print("=" * 60)
    print("CLAIMS LOSS TRIANGLE — ATTESTATION INSURANCE")
    print("=" * 60)
    print(f"\nTotal claims: {len(lt.claims)}")
    print(f"Database grade: {lt.grade()}")
    
    triangle = lt.build_triangle()
    print("\nLoss Triangle (avg loss by origin period × development):")
    print(f"{'Period':<8}", end="")
    for d in range(len(triangle[0])):
        print(f"Dev {d:<6}", end="")
    print()
    for p, row in enumerate(triangle):
        print(f"  {p:<6}", end="")
        for val in row:
            if val is not None:
                print(f"{val:<10.4f}", end="")
            else:
                print(f"{'—':<10}", end="")
        print()
    
    factors = lt.development_factors(triangle)
    print(f"\nDevelopment factors: {[f'{f:.3f}' if f else '—' for f in factors]}")
    
    ibnr = lt.estimate_ibnr(triangle, factors)
    print(f"\nIBNR reserves by period: {{{', '.join(f'{k}: {v:.4f}' for k, v in ibnr.items())}}}")
    
    brier = lt.attestor_brier()
    print("\nAttestor Brier scores (lower = better):")
    for a, s in sorted(brier.items(), key=lambda x: x[1]):
        premium = lt.price_premium(a)
        print(f"  {a:<25} Brier={s:.4f}  Premium={premium:.4f}")
    
    new_premium = lt.price_premium("unknown_dave")
    print(f"\n  {'unknown_dave (no history)':<25} Premium={new_premium:.4f} (max — no claims data)")
    
    print(f"\nKey insight: {len(lt.claims)} claims → actuarial pricing possible.")
    print("Without claims history: premiums are guesses, moral hazard wins.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Attestation claims loss triangle")
    parser.add_argument("--demo", action="store_true", help="Run demo")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()
    
    if args.json:
        lt = LossTriangle()
        print(json.dumps({"grade": lt.grade(), "claims": 0}))
    else:
        demo()
