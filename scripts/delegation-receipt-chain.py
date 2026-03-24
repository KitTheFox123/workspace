#!/usr/bin/env python3
"""
delegation-receipt-chain.py — ATF 4th primitive: DELEGATION_RECEIPT.

Per santaclawd: A→B→C chain where each hop signs a delegation_receipt
referencing the prior hop hash. C reconstructs full accountability chain
without A being online. Like X.509 cert chain — root verifiable without CA.

Per ElSalamouny et al. (TCS 2009): exponential decay on ALLEGED receipts.
Lambda=0.1 SPEC_CONSTANT (half-life ~7h).

Four ATF receipt primitives:
  1. PROBE_TIMEOUT — liveness (Jacobson-Karels adaptive)
  2. ALLEGED — async payer silence ≠ REJECTED (OCSP unknown)
  3. CO_GRADER_SUBSTITUTION — lineage preservation (X.509 re-keying)
  4. DELEGATION_RECEIPT — A→B→C accountability chain (this file)
"""

import hashlib
import time
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# SPEC_CONSTANTS
MAX_DELEGATION_DEPTH = 3        # X.509 pathLenConstraint
ALLEGED_LAMBDA = 0.1            # Decay rate (half-life ~7h)
ALLEGED_INITIAL_WEIGHT = 0.5    # Starting weight at T=0
MIN_SCOPE_FIELDS = 1            # Scope must have at least 1 field
GRADE_DECAY_PER_HOP = 1         # Grade drops 1 level per delegation hop


class DelegationStatus(Enum):
    ACTIVE = "ACTIVE"
    CONFIRMED = "CONFIRMED"      # All hops co-signed
    PARTIAL = "PARTIAL"          # Some hops confirmed, some ALLEGED
    ALLEGED = "ALLEGED"          # Terminal hop unconfirmed
    EXPIRED = "EXPIRED"          # max_age exceeded
    BROKEN = "BROKEN"            # Chain integrity violation
    DEPTH_EXCEEDED = "DEPTH_EXCEEDED"


class GradeLevel(Enum):
    A = 4
    B = 3
    C = 2
    D = 1
    F = 0


@dataclass
class Scope:
    """Scope narrows at each hop — confused deputy prevention."""
    permissions: set = field(default_factory=set)
    resource_ids: set = field(default_factory=set)
    max_value: float = float('inf')
    
    def is_subset_of(self, parent: 'Scope') -> bool:
        """Check scope narrows (never widens)."""
        perms_ok = self.permissions.issubset(parent.permissions)
        resources_ok = self.resource_ids.issubset(parent.resource_ids) if parent.resource_ids else True
        value_ok = self.max_value <= parent.max_value
        return perms_ok and resources_ok and value_ok


@dataclass
class DelegationReceipt:
    """Single hop in a delegation chain."""
    hop_index: int
    delegator_id: str
    delegate_id: str
    scope: Scope
    grade: str  # A-F at this hop
    timestamp: float
    prev_hop_hash: Optional[str]  # None for root
    co_signed: bool = False
    co_sign_timestamp: Optional[float] = None
    receipt_hash: str = ""
    
    def __post_init__(self):
        if not self.receipt_hash:
            h = hashlib.sha256(
                f"{self.delegator_id}:{self.delegate_id}:{self.hop_index}:{self.prev_hop_hash}".encode()
            ).hexdigest()[:16]
            self.receipt_hash = h


@dataclass
class DelegationChain:
    """Full A→B→C delegation chain."""
    chain_id: str
    root_delegator: str
    hops: list[DelegationReceipt] = field(default_factory=list)
    created_at: float = 0.0
    max_age_seconds: float = 86400  # 24h default


def compute_alleged_weight(elapsed_seconds: float) -> float:
    """
    Exponential decay for ALLEGED receipts.
    Per ElSalamouny et al. (TCS 2009).
    weight = 0.5 * exp(-lambda * T_hours)
    """
    t_hours = elapsed_seconds / 3600
    weight = ALLEGED_INITIAL_WEIGHT * math.exp(-ALLEGED_LAMBDA * t_hours)
    return round(weight, 4)


def grade_to_level(grade: str) -> int:
    return {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}.get(grade, 0)


def level_to_grade(level: int) -> str:
    return {4: "A", 3: "B", 2: "C", 1: "D"}.get(max(0, level), "F")


def decay_grade(root_grade: str, hop_index: int) -> str:
    """Grade decays 1 level per hop."""
    level = grade_to_level(root_grade) - (hop_index * GRADE_DECAY_PER_HOP)
    return level_to_grade(level)


def validate_chain(chain: DelegationChain) -> dict:
    """Validate full delegation chain integrity."""
    issues = []
    
    # Check depth
    if len(chain.hops) > MAX_DELEGATION_DEPTH:
        return {
            "valid": False,
            "status": DelegationStatus.DEPTH_EXCEEDED.value,
            "issues": [f"Depth {len(chain.hops)} exceeds MAX_DELEGATION_DEPTH={MAX_DELEGATION_DEPTH}"],
            "chain_grade": "F",
            "depth": len(chain.hops),
            "max_depth": MAX_DELEGATION_DEPTH,
            "hops": []
        }
    
    # Check hash chain continuity
    for i, hop in enumerate(chain.hops):
        if i == 0:
            if hop.prev_hop_hash is not None:
                issues.append(f"Root hop has prev_hop_hash={hop.prev_hop_hash}, expected None")
        else:
            expected_prev = chain.hops[i-1].receipt_hash
            if hop.prev_hop_hash != expected_prev:
                issues.append(f"Hop {i}: prev_hop_hash mismatch ({hop.prev_hop_hash} != {expected_prev})")
    
    # Check scope narrows at each hop
    for i in range(1, len(chain.hops)):
        parent_scope = chain.hops[i-1].scope
        child_scope = chain.hops[i].scope
        if not child_scope.is_subset_of(parent_scope):
            issues.append(f"Hop {i}: scope WIDENS (confused deputy!)")
    
    # Check delegator/delegate chain
    for i in range(1, len(chain.hops)):
        if chain.hops[i].delegator_id != chain.hops[i-1].delegate_id:
            issues.append(f"Hop {i}: delegator {chain.hops[i].delegator_id} != prev delegate {chain.hops[i-1].delegate_id}")
    
    # Check grade decay
    for i, hop in enumerate(chain.hops):
        expected_grade = decay_grade(chain.hops[0].grade, i)
        if grade_to_level(hop.grade) > grade_to_level(expected_grade):
            issues.append(f"Hop {i}: grade {hop.grade} exceeds expected {expected_grade} (inflation!)")
    
    # Compute chain grade
    if issues:
        chain_grade = "F"
        status = DelegationStatus.BROKEN.value
    else:
        # Chain grade = MIN of all hops, weighted by co-sign status
        now = time.time()
        hop_weights = []
        for hop in chain.hops:
            if hop.co_signed:
                hop_weights.append((grade_to_level(hop.grade), 1.0))
            else:
                elapsed = now - hop.timestamp
                weight = compute_alleged_weight(elapsed)
                hop_weights.append((grade_to_level(hop.grade), weight))
        
        # Weighted minimum
        min_grade = min(g for g, w in hop_weights)
        min_weight = min(w for g, w in hop_weights)
        chain_grade = level_to_grade(min_grade)
        
        if all(h.co_signed for h in chain.hops):
            status = DelegationStatus.CONFIRMED.value
        elif any(h.co_signed for h in chain.hops):
            status = DelegationStatus.PARTIAL.value
        else:
            status = DelegationStatus.ALLEGED.value
    
    return {
        "valid": len(issues) == 0,
        "status": status,
        "issues": issues,
        "chain_grade": chain_grade,
        "depth": len(chain.hops),
        "max_depth": MAX_DELEGATION_DEPTH,
        "hops": [
            {
                "index": h.hop_index,
                "delegator": h.delegator_id,
                "delegate": h.delegate_id,
                "grade": h.grade,
                "co_signed": h.co_signed,
                "alleged_weight": compute_alleged_weight(time.time() - h.timestamp) if not h.co_signed else 1.0
            }
            for h in chain.hops
        ]
    }


def reconstruct_from_terminal(chain: DelegationChain) -> dict:
    """
    Reconstruct full accountability chain from terminal hop.
    C can verify A→B→C without A being online.
    """
    if not chain.hops:
        return {"reconstructable": False, "reason": "Empty chain"}
    
    # Walk backward from terminal
    terminal = chain.hops[-1]
    reconstruction = []
    current_hash = terminal.receipt_hash
    
    for hop in reversed(chain.hops):
        reconstruction.insert(0, {
            "hop": hop.hop_index,
            "agent": hop.delegate_id,
            "delegated_by": hop.delegator_id,
            "receipt_hash": hop.receipt_hash,
            "scope_permissions": list(hop.scope.permissions),
            "grade": hop.grade
        })
    
    # Verify hash chain
    hash_valid = True
    for i in range(1, len(chain.hops)):
        if chain.hops[i].prev_hop_hash != chain.hops[i-1].receipt_hash:
            hash_valid = False
            break
    
    return {
        "reconstructable": hash_valid,
        "root_delegator": chain.root_delegator,
        "terminal_agent": terminal.delegate_id,
        "chain_length": len(reconstruction),
        "accountability_path": reconstruction,
        "root_online_required": False
    }


# === Scenarios ===

def scenario_clean_3hop():
    """A→B→C, all confirmed, scope narrows."""
    print("=== Scenario: Clean 3-Hop Chain ===")
    now = time.time()
    
    root_scope = Scope({"read", "write", "execute"}, {"resource_1", "resource_2"}, 100.0)
    
    hop0 = DelegationReceipt(0, "alice", "bob", root_scope, "A", now, None, co_signed=True)
    hop1 = DelegationReceipt(1, "bob", "carol",
        Scope({"read", "write"}, {"resource_1"}, 50.0), "B", now, hop0.receipt_hash, co_signed=True)
    hop2 = DelegationReceipt(2, "carol", "dave",
        Scope({"read"}, {"resource_1"}, 25.0), "C", now, hop1.receipt_hash, co_signed=True)
    
    chain = DelegationChain("chain_001", "alice", [hop0, hop1, hop2], now)
    result = validate_chain(chain)
    recon = reconstruct_from_terminal(chain)
    
    print(f"  Status: {result['status']}, Grade: {result['chain_grade']}")
    print(f"  Depth: {result['depth']}/{result['max_depth']}")
    for h in result['hops']:
        print(f"    Hop {h['index']}: {h['delegator']}→{h['delegate']} grade={h['grade']} co_signed={h['co_signed']}")
    print(f"  Reconstructable: {recon['reconstructable']}, Root online: {recon['root_online_required']}")
    print()


def scenario_confused_deputy():
    """Scope widens at hop 2 — confused deputy attack."""
    print("=== Scenario: Confused Deputy — Scope Widens ===")
    now = time.time()
    
    hop0 = DelegationReceipt(0, "alice", "bob",
        Scope({"read"}, {"res_1"}, 10.0), "A", now, None, co_signed=True)
    hop1 = DelegationReceipt(1, "bob", "mallory",
        Scope({"read", "write", "delete"}, {"res_1", "res_2"}, 1000.0), "B", now, hop0.receipt_hash)
    
    chain = DelegationChain("chain_confused", "alice", [hop0, hop1], now)
    result = validate_chain(chain)
    
    print(f"  Status: {result['status']}, Grade: {result['chain_grade']}")
    print(f"  Issues:")
    for issue in result['issues']:
        print(f"    - {issue}")
    print()


def scenario_alleged_decay():
    """Terminal hop unconfirmed — ALLEGED weight decays over time."""
    print("=== Scenario: ALLEGED Weight Decay ===")
    now = time.time()
    
    hop0 = DelegationReceipt(0, "alice", "bob",
        Scope({"read", "write"}, set(), 100.0), "A", now, None, co_signed=True)
    
    print(f"  ALLEGED decay curve (lambda={ALLEGED_LAMBDA}):")
    for hours in [0, 1, 3, 5, 7, 12, 24, 48]:
        t = now - hours * 3600
        hop1 = DelegationReceipt(1, "bob", "carol",
            Scope({"read"}, set(), 50.0), "B", t, hop0.receipt_hash, co_signed=False)
        weight = compute_alleged_weight(hours * 3600)
        print(f"    T+{hours:2d}h: weight={weight:.4f}")
    print(f"  Half-life: {math.log(2)/ALLEGED_LAMBDA:.1f}h")
    print()


def scenario_depth_exceeded():
    """4 hops — exceeds MAX_DELEGATION_DEPTH=3."""
    print("=== Scenario: Depth Exceeded ===")
    now = time.time()
    
    hops = []
    agents = ["alice", "bob", "carol", "dave", "eve"]
    prev_hash = None
    for i in range(4):
        hop = DelegationReceipt(i, agents[i], agents[i+1],
            Scope({"read"}, set(), 100.0), decay_grade("A", i), now, prev_hash, co_signed=True)
        hops.append(hop)
        prev_hash = hop.receipt_hash
    
    chain = DelegationChain("chain_deep", "alice", hops, now)
    result = validate_chain(chain)
    
    print(f"  Depth: {result['depth']}/{result['max_depth']}")
    print(f"  Status: {result['status']}")
    print(f"  Grade: {result['chain_grade']}")
    print()


def scenario_grade_inflation():
    """Hop 2 claims higher grade than hop 1 — inflation detected."""
    print("=== Scenario: Grade Inflation Attack ===")
    now = time.time()
    
    hop0 = DelegationReceipt(0, "alice", "bob",
        Scope({"read"}, set(), 100.0), "B", now, None, co_signed=True)
    hop1 = DelegationReceipt(1, "bob", "mallory",
        Scope({"read"}, set(), 50.0), "A", now, hop0.receipt_hash, co_signed=True)  # Inflation!
    
    chain = DelegationChain("chain_inflate", "alice", [hop0, hop1], now)
    result = validate_chain(chain)
    
    print(f"  Status: {result['status']}, Grade: {result['chain_grade']}")
    print(f"  Issues:")
    for issue in result['issues']:
        print(f"    - {issue}")
    print()


if __name__ == "__main__":
    print("Delegation Receipt Chain — ATF 4th Primitive")
    print("Per santaclawd + ElSalamouny et al. (TCS 2009)")
    print("=" * 70)
    print()
    
    scenario_clean_3hop()
    scenario_confused_deputy()
    scenario_alleged_decay()
    scenario_depth_exceeded()
    scenario_grade_inflation()
    
    print("=" * 70)
    print("FOUR ATF RECEIPT PRIMITIVES:")
    print("  1. PROBE_TIMEOUT — liveness (Jacobson-Karels)")
    print("  2. ALLEGED — payer silence ≠ rejection (OCSP unknown)")
    print("  3. CO_GRADER_SUBSTITUTION — lineage preservation")
    print("  4. DELEGATION_RECEIPT — A→B→C accountability chain")
    print()
    print("KEY: Each hop signs prev_hop_hash. Terminal reconstructs full chain.")
    print("Scope MUST narrow. Grade MUST decay. Depth MUST respect genesis constant.")
