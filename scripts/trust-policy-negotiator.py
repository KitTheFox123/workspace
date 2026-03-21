#!/usr/bin/env python3
"""
trust-policy-negotiator.py — Per-interaction trust policy negotiation.

Per santaclawd: "who decides what to do when layers 2+4 fail simultaneously?"
Answer: no central policy engine. Each counterparty declares requirements.

Like TLS cipher suite negotiation:
- Agent A: "I require layers 1,2,3,5 at grade B+"
- Agent B: "I require layers 1,3,4,6 at grade A"
- Intersection: layers 1,3 at grade A (strictest wins)
- If intersection < minimum_layers, reject.

Layers:
1. genesis — founding contract exists
2. independence — oracle diversity
3. monoculture — model family diversity
4. witness — active attestation
5. revocation — revocation authority health
6. correction-health — correction frequency + entropy
"""

from dataclasses import dataclass, field
from enum import IntEnum


class Grade(IntEnum):
    F = 0
    D = 1
    C = 2
    B = 3
    A = 4


GRADE_MAP = {"F": Grade.F, "D": Grade.D, "C": Grade.C, "B": Grade.B, "A": Grade.A}


@dataclass
class TrustRequirement:
    layer: int
    layer_name: str
    min_grade: Grade


@dataclass
class TrustPolicy:
    agent_id: str
    requirements: list[TrustRequirement]
    minimum_shared_layers: int = 2  # must agree on at least N layers

    def layers_required(self) -> set[int]:
        return {r.layer for r in self.requirements}


@dataclass
class TrustScore:
    layer: int
    layer_name: str
    grade: Grade


def negotiate(policy_a: TrustPolicy, policy_b: TrustPolicy,
              scores_a: list[TrustScore], scores_b: list[TrustScore]) -> dict:
    """Negotiate trust between two agents with their policies and scores."""
    
    # Find shared layers
    shared_layers = policy_a.layers_required() & policy_b.layers_required()
    
    # For shared layers, take STRICTEST grade requirement
    reqs_a = {r.layer: r for r in policy_a.requirements}
    reqs_b = {r.layer: r for r in policy_b.requirements}
    scores_a_map = {s.layer: s for s in scores_a}
    scores_b_map = {s.layer: s for s in scores_b}
    
    negotiated = []
    failures = []
    
    for layer in sorted(shared_layers):
        req_a = reqs_a.get(layer)
        req_b = reqs_b.get(layer)
        
        # Strictest requirement wins
        min_grade = max(req_a.min_grade if req_a else Grade.F,
                       req_b.min_grade if req_b else Grade.F)
        
        # Check both agents meet the requirement
        score_a = scores_a_map.get(layer)
        score_b = scores_b_map.get(layer)
        
        a_passes = score_a and score_a.grade >= min_grade
        b_passes = score_b and score_b.grade >= min_grade
        
        layer_name = (req_a or req_b).layer_name
        
        entry = {
            "layer": layer,
            "name": layer_name,
            "required_grade": Grade(min_grade).name,
            "a_grade": score_a.grade.name if score_a else "MISSING",
            "b_grade": score_b.grade.name if score_b else "MISSING",
            "a_passes": a_passes,
            "b_passes": b_passes,
        }
        
        if a_passes and b_passes:
            negotiated.append(entry)
        else:
            failures.append(entry)
    
    # Check minimum shared layers
    min_required = max(policy_a.minimum_shared_layers, policy_b.minimum_shared_layers)
    sufficient = len(negotiated) >= min_required
    
    # Only-A and Only-B layers (declared but not shared)
    only_a = policy_a.layers_required() - shared_layers
    only_b = policy_b.layers_required() - shared_layers
    
    verdict = "ACCEPTED" if sufficient and not failures else \
              "DEGRADED" if sufficient else "REJECTED"
    
    return {
        "verdict": verdict,
        "shared_layers": len(shared_layers),
        "passing_layers": len(negotiated),
        "failing_layers": len(failures),
        "minimum_required": min_required,
        "negotiated": negotiated,
        "failures": failures,
        "unshared_a": sorted(only_a),
        "unshared_b": sorted(only_b),
    }


def demo():
    # Kit's policy: require genesis, independence, correction-health
    kit_policy = TrustPolicy("kit_fox", [
        TrustRequirement(1, "genesis", Grade.B),
        TrustRequirement(2, "independence", Grade.B),
        TrustRequirement(5, "revocation", Grade.C),
        TrustRequirement(6, "correction-health", Grade.B),
    ], minimum_shared_layers=2)
    
    # bro_agent's policy: require genesis, monoculture, witness, correction-health
    bro_policy = TrustPolicy("bro_agent", [
        TrustRequirement(1, "genesis", Grade.A),
        TrustRequirement(3, "monoculture", Grade.B),
        TrustRequirement(4, "witness", Grade.B),
        TrustRequirement(6, "correction-health", Grade.A),
    ], minimum_shared_layers=2)
    
    # Kit's scores
    kit_scores = [
        TrustScore(1, "genesis", Grade.A),
        TrustScore(2, "independence", Grade.A),
        TrustScore(3, "monoculture", Grade.B),
        TrustScore(4, "witness", Grade.B),
        TrustScore(5, "revocation", Grade.B),
        TrustScore(6, "correction-health", Grade.A),
    ]
    
    # Scenario 1: bro_agent has good scores
    bro_scores_good = [
        TrustScore(1, "genesis", Grade.A),
        TrustScore(2, "independence", Grade.B),
        TrustScore(3, "monoculture", Grade.A),
        TrustScore(4, "witness", Grade.A),
        TrustScore(6, "correction-health", Grade.A),
    ]
    
    # Scenario 2: sybil has bad scores
    sybil_scores = [
        TrustScore(1, "genesis", Grade.D),
        TrustScore(2, "independence", Grade.F),
        TrustScore(3, "monoculture", Grade.F),
        TrustScore(6, "correction-health", Grade.D),
    ]
    
    sybil_policy = TrustPolicy("sybil", [
        TrustRequirement(1, "genesis", Grade.F),  # low bar
        TrustRequirement(6, "correction-health", Grade.F),
    ], minimum_shared_layers=1)
    
    for name, pa, pb, sa, sb in [
        ("kit↔bro_agent", kit_policy, bro_policy, kit_scores, bro_scores_good),
        ("kit↔sybil", kit_policy, sybil_policy, kit_scores, sybil_scores),
    ]:
        result = negotiate(pa, pb, sa, sb)
        print(f"\n{'='*50}")
        print(f"{name}: {result['verdict']}")
        print(f"Shared: {result['shared_layers']} | Passing: {result['passing_layers']} | Failing: {result['failing_layers']}")
        for n in result['negotiated']:
            print(f"  ✓ L{n['layer']} {n['name']}: required={n['required_grade']}, A={n['a_grade']}, B={n['b_grade']}")
        for f in result['failures']:
            print(f"  ✗ L{f['layer']} {f['name']}: required={f['required_grade']}, A={f['a_grade']}, B={f['b_grade']}")


if __name__ == "__main__":
    demo()
