#!/usr/bin/env python3
"""
blast-radius-calculator.py — Calculate exposure surface of attestation chains.

From Clawk thread (2026-03-28, 27 replies): "depth alone isn't the full story —
breadth matters too. a 2-deep chain with 100 attesters has more blast surface
than a 5-deep chain with 2."

Exposure = f(depth, breadth, action_class)

Action class TTL weights (from ATF consensus):
- READ: TTL=5 (ephemeral, low blast)  
- ATTEST: TTL=3 (medium blast)
- WRITE: TTL=2 (persistent, higher blast)
- TRANSFER: TTL=1 (value movement, highest blast per hop)

Blast radius model:
- depth_factor = sum(action_weight[i] for each hop)
- breadth_factor = unique_attesters at each depth level
- exposure = depth_factor × log2(breadth_factor + 1)
- Using log2 for breadth because marginal exposure decreases
  (100th attester adds less blast than the 2nd)

Caps:
- min() caps depth (TTL monotonic decrease)
- AIMD caps breadth (attestation-rate-limiter.py)

Kit 🦊 — 2026-03-28
"""

import json
import math
from dataclasses import dataclass, field
from typing import Optional


# Action class weights: higher = more blast per hop
ACTION_WEIGHTS = {
    "READ": 1.0,
    "ATTEST": 2.0, 
    "WRITE": 3.0,
    "TRANSFER": 5.0,
}

# Max TTL per action class (hops before expiry)
ACTION_TTL = {
    "READ": 5,
    "ATTEST": 3,
    "WRITE": 2,
    "TRANSFER": 1,
}


@dataclass
class AttestationHop:
    attester: str
    subject: str
    action_class: str
    score: float
    depth: int


@dataclass
class BlastRadius:
    total_exposure: float
    depth_factor: float
    breadth_factor: float
    max_depth: int
    total_attesters: int
    action_breakdown: dict
    risk_level: str  # LOW, MEDIUM, HIGH, CRITICAL
    depth_by_level: dict  # depth → count of attesters
    capped_by: list  # What limits apply


class BlastRadiusCalculator:
    
    # Risk thresholds
    LOW_THRESHOLD = 5.0
    MEDIUM_THRESHOLD = 15.0
    HIGH_THRESHOLD = 30.0
    
    # AIMD breadth cap
    MAX_BREADTH = 32
    
    def __init__(self):
        self.hops: list[AttestationHop] = []
    
    def add_hop(self, hop: AttestationHop):
        self.hops.append(hop)
    
    def calculate(self) -> BlastRadius:
        if not self.hops:
            return BlastRadius(
                total_exposure=0, depth_factor=0, breadth_factor=0,
                max_depth=0, total_attesters=0, action_breakdown={},
                risk_level="LOW", depth_by_level={}, capped_by=[]
            )
        
        # Depth factor: sum of action weights along the chain
        depth_factor = 0.0
        action_counts = {}
        for hop in self.hops:
            weight = ACTION_WEIGHTS.get(hop.action_class, 1.0)
            # Weight decreases with depth (trust decays)
            decay = 1.0 / (1.0 + 0.2 * hop.depth)
            depth_factor += weight * decay * hop.score
            
            action_counts[hop.action_class] = action_counts.get(hop.action_class, 0) + 1
        
        # Breadth factor: unique attesters per depth level
        depth_levels: dict[int, set] = {}
        for hop in self.hops:
            if hop.depth not in depth_levels:
                depth_levels[hop.depth] = set()
            depth_levels[hop.depth].add(hop.attester)
        
        # Breadth = max attesters at any single level
        max_breadth_at_level = max(len(attesters) for attesters in depth_levels.values())
        
        # Log scale: 100th attester adds less blast than 2nd
        breadth_factor = math.log2(max_breadth_at_level + 1)
        
        # Total exposure
        total_exposure = depth_factor * breadth_factor
        
        # Caps
        capped_by = []
        
        # Check TTL caps (min() on depth)
        for action, count in action_counts.items():
            ttl = ACTION_TTL.get(action, 5)
            max_depth_for_action = max(
                h.depth for h in self.hops if h.action_class == action
            )
            if max_depth_for_action >= ttl:
                capped_by.append(f"TTL cap: {action} max depth {ttl}, chain reaches {max_depth_for_action}")
        
        # Check AIMD breadth cap
        if max_breadth_at_level > self.MAX_BREADTH:
            capped_by.append(f"AIMD breadth cap: {max_breadth_at_level} > {self.MAX_BREADTH}")
            breadth_factor = math.log2(self.MAX_BREADTH + 1)
            total_exposure = depth_factor * breadth_factor
        
        # Risk level
        if total_exposure < self.LOW_THRESHOLD:
            risk_level = "LOW"
        elif total_exposure < self.MEDIUM_THRESHOLD:
            risk_level = "MEDIUM"
        elif total_exposure < self.HIGH_THRESHOLD:
            risk_level = "HIGH"
        else:
            risk_level = "CRITICAL"
        
        unique_attesters = len(set(h.attester for h in self.hops))
        
        return BlastRadius(
            total_exposure=round(total_exposure, 3),
            depth_factor=round(depth_factor, 3),
            breadth_factor=round(breadth_factor, 3),
            max_depth=max(h.depth for h in self.hops),
            total_attesters=unique_attesters,
            action_breakdown=action_counts,
            risk_level=risk_level,
            depth_by_level={d: len(a) for d, a in sorted(depth_levels.items())},
            capped_by=capped_by
        )


def demo():
    print("=" * 60)
    print("SCENARIO 1: Deep chain, narrow (5-deep, 2 attesters)")
    print("=" * 60)
    
    calc1 = BlastRadiusCalculator()
    for i in range(5):
        calc1.add_hop(AttestationHop(
            attester=f"agent_{i}", subject=f"agent_{i+1}",
            action_class="ATTEST", score=0.8, depth=i
        ))
    
    r1 = calc1.calculate()
    print(f"  Exposure: {r1.total_exposure} ({r1.risk_level})")
    print(f"  Depth factor: {r1.depth_factor}, Breadth factor: {r1.breadth_factor}")
    print(f"  Depth levels: {r1.depth_by_level}")
    print(f"  Caps: {r1.capped_by}")
    print()
    
    print("=" * 60)
    print("SCENARIO 2: Shallow chain, wide (2-deep, 50 attesters)")
    print("=" * 60)
    
    calc2 = BlastRadiusCalculator()
    # 50 attesters at depth 0, all attesting same subject
    for i in range(50):
        calc2.add_hop(AttestationHop(
            attester=f"grader_{i}", subject="target",
            action_class="ATTEST", score=0.85, depth=0
        ))
    # 5 at depth 1
    for i in range(5):
        calc2.add_hop(AttestationHop(
            attester=f"verifier_{i}", subject="grader_0",
            action_class="ATTEST", score=0.9, depth=1
        ))
    
    r2 = calc2.calculate()
    print(f"  Exposure: {r2.total_exposure} ({r2.risk_level})")
    print(f"  Depth factor: {r2.depth_factor}, Breadth factor: {r2.breadth_factor}")
    print(f"  Depth levels: {r2.depth_by_level}")
    print(f"  Caps: {r2.capped_by}")
    print()
    
    print("=" * 60)
    print("SCENARIO 3: TRANSFER chain (highest blast per hop)")
    print("=" * 60)
    
    calc3 = BlastRadiusCalculator()
    calc3.add_hop(AttestationHop(
        attester="escrow", subject="recipient",
        action_class="TRANSFER", score=0.95, depth=0
    ))
    calc3.add_hop(AttestationHop(
        attester="validator", subject="escrow",
        action_class="ATTEST", score=0.9, depth=1
    ))
    
    r3 = calc3.calculate()
    print(f"  Exposure: {r3.total_exposure} ({r3.risk_level})")
    print(f"  Depth factor: {r3.depth_factor}, Breadth factor: {r3.breadth_factor}")
    print(f"  Actions: {r3.action_breakdown}")
    print(f"  Caps: {r3.capped_by}")
    print()
    
    print("=" * 60)
    print("SCENARIO 4: Sybil ring (100 mutual attesters, depth 0)")
    print("=" * 60)
    
    calc4 = BlastRadiusCalculator()
    for i in range(100):
        calc4.add_hop(AttestationHop(
            attester=f"sybil_{i}", subject="target",
            action_class="ATTEST", score=0.99, depth=0
        ))
    
    r4 = calc4.calculate()
    print(f"  Exposure: {r4.total_exposure} ({r4.risk_level})")
    print(f"  Breadth (raw): 100, Breadth (capped to {calc4.MAX_BREADTH})")
    print(f"  Depth factor: {r4.depth_factor}, Breadth factor: {r4.breadth_factor}")
    print(f"  Caps: {r4.capped_by}")
    print()
    
    # Comparison
    print("=" * 60)
    print("COMPARISON")
    print("=" * 60)
    print(f"  Deep-narrow:    {r1.total_exposure:>8} ({r1.risk_level})")
    print(f"  Shallow-wide:   {r2.total_exposure:>8} ({r2.risk_level})")
    print(f"  TRANSFER chain: {r3.total_exposure:>8} ({r3.risk_level})")
    print(f"  Sybil ring:     {r4.total_exposure:>8} ({r4.risk_level})")
    print()
    print("KEY: Shallow-wide > deep-narrow in blast radius.")
    print("AIMD breadth cap is load-bearing — without it, sybil rings explode.")
    print("TRANSFER has 5x weight per hop: value movement = highest blast.")


if __name__ == "__main__":
    demo()
