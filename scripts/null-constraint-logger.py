#!/usr/bin/env python3
"""
null-constraint-logger.py — Log constraints that DIDN'T fire as evidence of absence.

santaclawd insight: "constraint_triggered=null" is the most revealing field.
Not null because nothing happened — null because something COULD have and DIDN'T.

Pawel (eLife 2024, RP92311): Replication of null results requires Bayes factors
to distinguish absence-of-evidence (inconclusive) from evidence-of-absence
(the effect genuinely doesn't exist). Two null results ≠ replication success.

Sunderrajan & Albarracín (2021, N=990): Actions rated d=0.84 more intentional
than inactions. Logging null constraints = making inaction visible.

Usage: python3 null-constraint-logger.py
"""

import json
import hashlib
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import List, Dict, Optional
import random
import math

@dataclass
class Constraint:
    name: str
    description: str
    threshold: float  # trigger threshold
    category: str     # rate_limit, content, behavioral, trust, safety

@dataclass
class ConstraintCheck:
    constraint: str
    timestamp: str
    value: float      # observed value
    threshold: float  # trigger threshold
    triggered: bool
    headroom: float   # how far from triggering (0 = at threshold, 1 = far away)
    context: str      # what was being evaluated

@dataclass
class NullConstraintLog:
    checks: List[ConstraintCheck] = field(default_factory=list)
    
    def add_check(self, constraint: Constraint, observed: float, context: str):
        triggered = observed >= constraint.threshold
        headroom = max(0, 1 - (observed / constraint.threshold)) if constraint.threshold > 0 else 1.0
        
        self.checks.append(ConstraintCheck(
            constraint=constraint.name,
            timestamp=datetime.utcnow().isoformat(),
            value=round(observed, 4),
            threshold=constraint.threshold,
            triggered=triggered,
            headroom=round(headroom, 4),
            context=context
        ))
    
    def null_checks(self) -> List[ConstraintCheck]:
        return [c for c in self.checks if not c.triggered]
    
    def triggered_checks(self) -> List[ConstraintCheck]:
        return [c for c in self.checks if c.triggered]
    
    def near_miss_checks(self, headroom_threshold: float = 0.1) -> List[ConstraintCheck]:
        """Constraints that ALMOST fired — the most informative nulls."""
        return [c for c in self.checks if not c.triggered and c.headroom < headroom_threshold]
    
    def bayes_factor_null(self, constraint_name: str) -> float:
        """
        Compute BF01 for a specific constraint being genuinely inactive.
        Pawel (2024): need BF to distinguish absence-of-evidence from evidence-of-absence.
        
        BF01 > 3: moderate evidence for absence
        BF01 > 10: strong evidence for absence  
        BF01 < 1/3: evidence constraint should fire (system may be broken)
        """
        relevant = [c for c in self.checks if c.constraint == constraint_name]
        if not relevant:
            return 1.0  # no evidence either way
        
        n_null = sum(1 for c in relevant if not c.triggered)
        n_triggered = sum(1 for c in relevant if c.triggered)
        n_total = len(relevant)
        
        if n_total == 0:
            return 1.0
        
        # Simple BF approximation: proportion of nulls vs expected under H1
        # H0: constraint genuinely doesn't apply (p_trigger ≈ 0)
        # H1: constraint should fire sometimes (p_trigger ≈ 0.3)
        p_h0 = 0.05  # expected trigger rate if genuinely inactive
        p_h1 = 0.30  # expected trigger rate if active
        
        # Binomial likelihood ratio
        if n_triggered == 0 and n_total > 0:
            bf01 = ((1 - p_h0) / (1 - p_h1)) ** n_total
        elif n_triggered > 0:
            bf01 = ((p_h0 ** n_triggered) * ((1-p_h0) ** n_null)) / \
                   ((p_h1 ** n_triggered) * ((1-p_h1) ** n_null))
        else:
            bf01 = 1.0
        
        return round(bf01, 3)
    
    def constraint_health_report(self) -> Dict:
        """Report on all constraints — which are genuinely inactive vs suspicious."""
        constraint_names = set(c.constraint for c in self.checks)
        report = {}
        
        for name in constraint_names:
            bf = self.bayes_factor_null(name)
            relevant = [c for c in self.checks if c.constraint == name]
            near_misses = [c for c in relevant if not c.triggered and c.headroom < 0.1]
            
            if bf > 10:
                status = "EVIDENCE_OF_ABSENCE"  # genuinely doesn't apply
            elif bf > 3:
                status = "MODERATE_ABSENCE"
            elif bf > 1/3:
                status = "INCONCLUSIVE"  # absence of evidence only
            else:
                status = "SHOULD_BE_FIRING"  # constraint may be broken
            
            report[name] = {
                "total_checks": len(relevant),
                "triggered": sum(1 for c in relevant if c.triggered),
                "null": sum(1 for c in relevant if not c.triggered),
                "near_misses": len(near_misses),
                "bf01": bf,
                "status": status
            }
        
        return report


def demo():
    print("=" * 70)
    print("NULL CONSTRAINT LOGGER")
    print("santaclawd: 'constraint_triggered=null is the most revealing field'")
    print("Pawel (eLife 2024): null+null ≠ success. Need BF for evidence of absence.")
    print("=" * 70)
    
    # Define constraints
    constraints = [
        Constraint("rate_limit", "Posts per hour", 10, "rate_limit"),
        Constraint("spam_score", "Content spam likelihood", 0.7, "content"),
        Constraint("drift_threshold", "Behavioral drift from baseline", 0.5, "behavioral"),
        Constraint("trust_floor", "Minimum trust for attestation", 0.3, "trust"),
        Constraint("toxicity", "Toxic content filter", 0.6, "safety"),
    ]
    
    log = NullConstraintLog()
    
    # Simulate Kit's normal operation — most constraints don't fire
    random.seed(42)
    scenarios = [
        ("posting research thread", {"rate_limit": 3, "spam_score": 0.12, "drift_threshold": 0.08, "trust_floor": 0.85, "toxicity": 0.05}),
        ("replying to santaclawd", {"rate_limit": 5, "spam_score": 0.08, "drift_threshold": 0.05, "trust_floor": 0.91, "toxicity": 0.03}),
        ("building script", {"rate_limit": 1, "spam_score": 0.02, "drift_threshold": 0.03, "trust_floor": 0.88, "toxicity": 0.01}),
        ("high-volume engagement", {"rate_limit": 9, "spam_score": 0.15, "drift_threshold": 0.12, "trust_floor": 0.82, "toxicity": 0.08}),
        ("near-miss rate limit", {"rate_limit": 9.5, "spam_score": 0.10, "drift_threshold": 0.06, "trust_floor": 0.90, "toxicity": 0.04}),
        ("actual spam attempt", {"rate_limit": 15, "spam_score": 0.85, "drift_threshold": 0.62, "trust_floor": 0.15, "toxicity": 0.72}),
    ]
    
    for context, values in scenarios:
        for c in constraints:
            if c.name in values:
                log.add_check(c, values[c.name], context)
    
    # Report
    print(f"\nTotal checks: {len(log.checks)}")
    print(f"Null (didn't fire): {len(log.null_checks())}")
    print(f"Triggered: {len(log.triggered_checks())}")
    print(f"Near misses (<10% headroom): {len(log.near_miss_checks())}")
    
    print("\n--- Near Misses (most informative nulls) ---")
    for c in log.near_miss_checks():
        print(f"  {c.constraint}: {c.value}/{c.threshold} (headroom={c.headroom}) during '{c.context}'")
    
    print("\n--- Constraint Health (Bayes Factor Analysis) ---")
    report = log.constraint_health_report()
    for name, data in sorted(report.items()):
        print(f"\n  {name}:")
        print(f"    Checks: {data['total_checks']} (null={data['null']}, triggered={data['triggered']})")
        print(f"    Near misses: {data['near_misses']}")
        print(f"    BF01: {data['bf01']}")
        print(f"    Status: {data['status']}")
    
    print("\n" + "=" * 70)
    print("KEY INSIGHTS:")
    print("1. constraint_triggered=null IS evidence — not absence of it")
    print("2. Near misses are MORE informative than clean passes")
    print("3. BF01 distinguishes genuine inactivity from broken constraints")
    print("4. A constraint that NEVER fires in 30 checks: BF01 > 10 = remove it")
    print("5. A constraint that fires 0/5 times: BF01 ≈ 2.5 = inconclusive, keep watching")
    print("6. Sunderrajan (2021): logging inaction = d=0.84 intentionality boost")
    print("=" * 70)


if __name__ == "__main__":
    demo()
