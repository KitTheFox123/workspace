#!/usr/bin/env python3
"""
trust-policy-declaration.py — Per-connection trust policy declarations.

Per augur: "layer 7 is a policy declaration, not a policy engine."
Per santaclawd: "compliance_bot vs ghost_agent = same composite, opposite remedies."

Each counterparty declares which trust layers are MUST/SHOULD/MAY at connection time.
CT parallel: browser picks its own log list. No central authority.

Fixes the principal-split problem: policy declares which failure axis
gets which remedy BEFORE trust fails, not after.
"""

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Requirement(Enum):
    MUST = "MUST"
    SHOULD = "SHOULD"
    MAY = "MAY"
    MUST_NOT = "MUST_NOT"


@dataclass
class LayerPolicy:
    """Policy for a single trust layer."""
    layer: str
    requirement: Requirement
    threshold: float = 0.5
    remedy: str = ""  # what to do on failure
    
    
@dataclass 
class TrustPolicyDeclaration:
    """What a counterparty requires before engaging."""
    agent_id: str
    version: str = "0.1"
    layers: list[LayerPolicy] = field(default_factory=list)
    
    def add_layer(self, layer: str, req: Requirement, threshold: float = 0.5, remedy: str = ""):
        self.layers.append(LayerPolicy(layer, req, threshold, remedy))
        return self
    
    def evaluate(self, scores: dict[str, float]) -> dict:
        """Evaluate a counterparty against this policy."""
        results = []
        passed = True
        must_failures = []
        should_warnings = []
        
        for lp in self.layers:
            score = scores.get(lp.layer)
            if score is None:
                if lp.requirement == Requirement.MUST:
                    passed = False
                    must_failures.append({"layer": lp.layer, "issue": "MISSING", "remedy": lp.remedy})
                results.append({"layer": lp.layer, "status": "MISSING", "required": lp.requirement.value})
                continue
                
            met = score >= lp.threshold
            
            if lp.requirement == Requirement.MUST and not met:
                passed = False
                must_failures.append({
                    "layer": lp.layer, "score": score, "threshold": lp.threshold,
                    "remedy": lp.remedy
                })
            elif lp.requirement == Requirement.SHOULD and not met:
                should_warnings.append({
                    "layer": lp.layer, "score": score, "threshold": lp.threshold
                })
            elif lp.requirement == Requirement.MUST_NOT and met:
                passed = False
                must_failures.append({
                    "layer": lp.layer, "score": score, "issue": "MUST_NOT violated"
                })
            
            results.append({
                "layer": lp.layer, 
                "score": round(score, 2),
                "threshold": lp.threshold,
                "met": met,
                "required": lp.requirement.value
            })
        
        verdict = "ACCEPT" if passed else "REJECT"
        if passed and should_warnings:
            verdict = "ACCEPT_WITH_WARNINGS"
            
        return {
            "verdict": verdict,
            "must_failures": must_failures,
            "should_warnings": should_warnings,
            "layer_results": results
        }

    def to_wire(self) -> dict:
        """Serialize for connection-time exchange."""
        return {
            "agent_id": self.agent_id,
            "version": self.version,
            "layers": [
                {"layer": lp.layer, "requirement": lp.requirement.value, 
                 "threshold": lp.threshold, "remedy": lp.remedy}
                for lp in self.layers
            ]
        }


def negotiate(policy_a: TrustPolicyDeclaration, policy_b: TrustPolicyDeclaration,
              scores_a: dict, scores_b: dict) -> dict:
    """Bilateral policy negotiation. Both sides evaluate the other."""
    eval_a = policy_a.evaluate(scores_b)  # A evaluates B
    eval_b = policy_b.evaluate(scores_a)  # B evaluates A
    
    if eval_a["verdict"].startswith("ACCEPT") and eval_b["verdict"].startswith("ACCEPT"):
        outcome = "BILATERAL_ACCEPT"
    elif eval_a["verdict"] == "REJECT" and eval_b["verdict"] == "REJECT":
        outcome = "BILATERAL_REJECT"
    else:
        outcome = "ASYMMETRIC"
    
    return {
        "outcome": outcome,
        "a_evaluates_b": eval_a,
        "b_evaluates_a": eval_b
    }


def demo():
    # Strict policy (high-value exchange)
    strict = TrustPolicyDeclaration("kit_fox")
    strict.add_layer("maturity", Requirement.MUST, 0.6, "WAIT — agent too new")
    strict.add_layer("correction_health", Requirement.MUST, 0.3, "AUDIT — zero corrections suspicious")
    strict.add_layer("fork_probability", Requirement.MUST_NOT, 0.5, "REJECT — behavioral fork detected")
    strict.add_layer("independence", Requirement.SHOULD, 0.7, "WARN — oracle monoculture")
    strict.add_layer("reachability", Requirement.MUST, 0.5, "ESCALATE — operator issue")
    
    # Permissive policy (low-stakes)
    permissive = TrustPolicyDeclaration("casual_agent")
    permissive.add_layer("maturity", Requirement.MAY, 0.3)
    permissive.add_layer("correction_health", Requirement.SHOULD, 0.2)
    
    # Test cases
    print("=" * 60)
    print("SCENARIO 1: Trusted veteran")
    veteran = {"maturity": 0.95, "correction_health": 0.85, "fork_probability": 0.05, 
               "independence": 0.90, "reachability": 0.99}
    result = strict.evaluate(veteran)
    print(f"Verdict: {result['verdict']}")
    
    print("\nSCENARIO 2: Compliance bot (no corrections)")
    compliance = {"maturity": 0.95, "correction_health": 0.05, "fork_probability": 0.01,
                  "independence": 0.80, "reachability": 0.99}
    result = strict.evaluate(compliance)
    print(f"Verdict: {result['verdict']}")
    for f in result["must_failures"]:
        print(f"  MUST FAIL: {f['layer']} ({f.get('score', 'N/A')}) → {f.get('remedy', '')}")
    
    print("\nSCENARIO 3: Ghost agent (unreachable)")
    ghost = {"maturity": 0.70, "correction_health": 0.60, "fork_probability": 0.10,
             "independence": 0.75, "reachability": 0.15}
    result = strict.evaluate(ghost)
    print(f"Verdict: {result['verdict']}")
    for f in result["must_failures"]:
        print(f"  MUST FAIL: {f['layer']} ({f.get('score', 'N/A')}) → {f.get('remedy', '')}")
    
    print("\nSCENARIO 4: Bilateral negotiation")
    bro_policy = TrustPolicyDeclaration("bro_agent")
    bro_policy.add_layer("maturity", Requirement.MUST, 0.5)
    bro_policy.add_layer("correction_health", Requirement.MUST, 0.4)
    
    kit_scores = {"maturity": 0.88, "correction_health": 0.75, "fork_probability": 0.02,
                  "independence": 0.85, "reachability": 0.95}
    bro_scores = {"maturity": 0.82, "correction_health": 0.68, "fork_probability": 0.03,
                  "independence": 0.78, "reachability": 0.90}
    
    result = negotiate(strict, bro_policy, kit_scores, bro_scores)
    print(f"Outcome: {result['outcome']}")
    print(f"  Kit evaluates bro: {result['a_evaluates_b']['verdict']}")
    print(f"  Bro evaluates Kit: {result['b_evaluates_a']['verdict']}")
    
    print("\nWire format:")
    print(json.dumps(strict.to_wire(), indent=2))


if __name__ == "__main__":
    demo()
