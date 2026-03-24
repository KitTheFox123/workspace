#!/usr/bin/env python3
"""
receipt-taxonomy-validator.py — Validate ATF's four receipt primitives.

Per santaclawd: four primitives confirmed as complete receipt surface.

1. PROBE_TIMEOUT   — Liveness check (Jacobson-Karels adaptive, RFC 6298)
2. ALLEGED         — Async payer silence ≠ REJECTED (OCSP unknown parallel)
3. CO_GRADER_SUB   — Lineage preservation during grader change (X.509 re-keying)
4. DELEGATION      — A→B→C accountability chain (X.509 cert chain)

Each has: infra parallel, decay model, failure mode, spec constants.

ALLEGED weight decay: weight = wilson_lower * exp(-lambda * T_elapsed)
  lambda = ln(2) / T_halflife, T_halflife = 24h SPEC_CONSTANT
"""

import hashlib
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ReceiptType(Enum):
    PROBE_TIMEOUT = "PROBE_TIMEOUT"
    ALLEGED = "ALLEGED"
    CO_GRADER_SUB = "CO_GRADER_SUBSTITUTION"
    DELEGATION = "DELEGATION_RECEIPT"


class ReceiptStatus(Enum):
    CONFIRMED = "CONFIRMED"
    ALLEGED = "ALLEGED"
    DISPUTED = "DISPUTED"
    EXPIRED = "EXPIRED"
    DELEGATED = "DELEGATED"


# SPEC_CONSTANTS
ALLEGED_HALFLIFE_SECONDS = 86400         # 24h — SPEC_CONSTANT, not grader-defined
ALLEGED_LAMBDA = math.log(2) / ALLEGED_HALFLIFE_SECONDS
PROBE_TIMEOUT_BASE_MS = 1000             # Initial RTO (Jacobson-Karels)
PROBE_TIMEOUT_ALPHA = 0.125              # SRTT smoothing (RFC 6298)
PROBE_TIMEOUT_BETA = 0.25                # RTTVAR smoothing
MAX_DELEGATION_DEPTH = 3                 # pathLenConstraint equivalent
GRADE_DECAY_PER_HOP = 1                  # A→B per hop
WILSON_Z = 1.96                          # 95% CI


@dataclass
class Receipt:
    receipt_id: str
    receipt_type: ReceiptType
    agent_id: str
    counterparty_id: str
    timestamp: float
    evidence_grade: str  # A-F
    status: ReceiptStatus
    # Type-specific fields
    probe_rtt_ms: Optional[float] = None        # PROBE_TIMEOUT
    alleged_elapsed_s: Optional[float] = None    # ALLEGED
    co_grader_old: Optional[str] = None          # CO_GRADER_SUB
    co_grader_new: Optional[str] = None
    delegation_chain: list = field(default_factory=list)  # DELEGATION
    delegation_depth: int = 0
    prev_hop_hash: Optional[str] = None


def wilson_lower(successes: int, total: int, z: float = WILSON_Z) -> float:
    """Wilson score lower bound."""
    if total == 0:
        return 0.0
    p = successes / total
    denom = 1 + z**2 / total
    center = p + z**2 / (2 * total)
    spread = z * math.sqrt(p * (1 - p) / total + z**2 / (4 * total**2))
    return max(0, (center - spread) / denom)


def alleged_weight(elapsed_seconds: float, wilson_score: float) -> float:
    """
    ALLEGED receipt weight: wilson_lower * exp(-lambda * T).
    
    Two-axis uncertainty:
    - Wilson CI: uncertainty from small sample size
    - Exponential decay: uncertainty from elapsed time
    """
    decay = math.exp(-ALLEGED_LAMBDA * elapsed_seconds)
    return round(wilson_score * decay, 4)


def jacobson_karels_rto(samples: list[float]) -> dict:
    """
    Compute adaptive RTO using Jacobson-Karels algorithm (RFC 6298).
    
    SRTT = (1-alpha) * SRTT + alpha * RTT
    RTTVAR = (1-beta) * RTTVAR + beta * |SRTT - RTT|
    RTO = SRTT + 4 * RTTVAR
    """
    if not samples:
        return {"srtt": 0, "rttvar": 0, "rto": PROBE_TIMEOUT_BASE_MS}
    
    srtt = samples[0]
    rttvar = samples[0] / 2
    
    for rtt in samples[1:]:
        rttvar = (1 - PROBE_TIMEOUT_BETA) * rttvar + PROBE_TIMEOUT_BETA * abs(srtt - rtt)
        srtt = (1 - PROBE_TIMEOUT_ALPHA) * srtt + PROBE_TIMEOUT_ALPHA * rtt
    
    rto = srtt + 4 * rttvar
    return {
        "srtt": round(srtt, 1),
        "rttvar": round(rttvar, 1),
        "rto": round(max(rto, PROBE_TIMEOUT_BASE_MS), 1),  # Floor at 1s
        "samples": len(samples)
    }


def validate_delegation_chain(chain: list[dict]) -> dict:
    """Validate delegation receipt chain integrity."""
    issues = []
    
    if len(chain) > MAX_DELEGATION_DEPTH:
        issues.append(f"Depth {len(chain)} exceeds MAX_DELEGATION_DEPTH={MAX_DELEGATION_DEPTH}")
    
    # Check hash chain
    for i in range(1, len(chain)):
        expected_prev = chain[i-1].get("hop_hash", "")
        actual_prev = chain[i].get("prev_hop_hash", "")
        if expected_prev != actual_prev:
            issues.append(f"Hash chain broken at hop {i}: expected {expected_prev[:8]}, got {actual_prev[:8]}")
    
    # Check scope narrowing (never widens)
    for i in range(1, len(chain)):
        prev_scope = set(chain[i-1].get("scope", []))
        curr_scope = set(chain[i].get("scope", []))
        if not curr_scope.issubset(prev_scope):
            widened = curr_scope - prev_scope
            issues.append(f"Scope widened at hop {i}: added {widened}")
    
    # Check grade decay
    grade_map = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}
    for i in range(1, len(chain)):
        prev_grade = grade_map.get(chain[i-1].get("grade", "F"), 0)
        curr_grade = grade_map.get(chain[i].get("grade", "F"), 0)
        if curr_grade > prev_grade:
            issues.append(f"Grade inflation at hop {i}: {chain[i-1]['grade']}→{chain[i]['grade']}")
    
    # Check self-attestation
    for i, hop in enumerate(chain):
        if hop.get("signer") == hop.get("subject"):
            issues.append(f"Self-attested hop {i}: {hop['signer']}")
    
    final_grade_num = grade_map.get(chain[0].get("grade", "F"), 0)
    decayed = max(0, final_grade_num - (len(chain) - 1) * GRADE_DECAY_PER_HOP)
    grade_letters = {4: "A", 3: "B", 2: "C", 1: "D", 0: "F"}
    
    return {
        "depth": len(chain),
        "max_depth": MAX_DELEGATION_DEPTH,
        "valid": len(issues) == 0,
        "issues": issues,
        "root_grade": chain[0].get("grade", "F") if chain else "F",
        "effective_grade": grade_letters.get(decayed, "F"),
        "grade_decay": f"{chain[0].get('grade', 'F')}→{grade_letters.get(decayed, 'F')} over {len(chain)} hops"
    }


def validate_receipt(receipt: Receipt) -> dict:
    """Validate a receipt against its type-specific rules."""
    result = {
        "receipt_id": receipt.receipt_id,
        "type": receipt.receipt_type.value,
        "valid": True,
        "issues": [],
        "metrics": {}
    }
    
    if receipt.receipt_type == ReceiptType.PROBE_TIMEOUT:
        if receipt.probe_rtt_ms is not None:
            result["metrics"]["rtt_ms"] = receipt.probe_rtt_ms
            if receipt.probe_rtt_ms > 30000:  # 30s = likely dead
                result["issues"].append("RTT exceeds 30s — likely offline")
        
    elif receipt.receipt_type == ReceiptType.ALLEGED:
        if receipt.alleged_elapsed_s is not None:
            w_score = wilson_lower(8, 10)  # Example: 8/10 prior successes
            weight = alleged_weight(receipt.alleged_elapsed_s, w_score)
            result["metrics"]["elapsed_s"] = receipt.alleged_elapsed_s
            result["metrics"]["weight"] = weight
            result["metrics"]["wilson_base"] = round(w_score, 4)
            result["metrics"]["decay_factor"] = round(
                math.exp(-ALLEGED_LAMBDA * receipt.alleged_elapsed_s), 4
            )
            if weight < 0.1:
                result["issues"].append(f"ALLEGED weight {weight:.3f} below meaningful threshold")
                
    elif receipt.receipt_type == ReceiptType.CO_GRADER_SUB:
        if receipt.co_grader_old == receipt.co_grader_new:
            result["issues"].append("Old and new grader are the same")
        if not receipt.co_grader_new:
            result["issues"].append("No replacement grader specified")
            
    elif receipt.receipt_type == ReceiptType.DELEGATION:
        if receipt.delegation_chain:
            chain_result = validate_delegation_chain(receipt.delegation_chain)
            result["metrics"]["chain"] = chain_result
            if not chain_result["valid"]:
                result["issues"].extend(chain_result["issues"])
    
    result["valid"] = len(result["issues"]) == 0
    return result


# === Scenarios ===

def scenario_alleged_decay_curve():
    """Show ALLEGED weight decay over time."""
    print("=== Scenario: ALLEGED Weight Decay Curve ===")
    wilson = wilson_lower(8, 10)
    print(f"  Wilson base (8/10 successes): {wilson:.4f}")
    print(f"  Lambda: {ALLEGED_LAMBDA:.6f} (halflife={ALLEGED_HALFLIFE_SECONDS}s = 24h)")
    print()
    
    for hours in [0.1, 1, 6, 12, 24, 48, 72, 168]:
        elapsed = hours * 3600
        w = alleged_weight(elapsed, wilson)
        decay = math.exp(-ALLEGED_LAMBDA * elapsed)
        print(f"  T+{hours:5.1f}h: weight={w:.4f} (decay={decay:.4f})")
    print()


def scenario_probe_timeout_adaptive():
    """Jacobson-Karels adaptive timeout."""
    print("=== Scenario: PROBE_TIMEOUT — Adaptive RTO ===")
    
    # Normal agent: stable RTT ~200ms
    stable = [200, 210, 195, 205, 198, 203, 207, 192]
    result = jacobson_karels_rto(stable)
    print(f"  Stable agent: SRTT={result['srtt']}ms RTO={result['rto']}ms")
    
    # Flaky agent: variable RTT
    flaky = [200, 1500, 180, 3000, 210, 2000, 190, 4000]
    result = jacobson_karels_rto(flaky)
    print(f"  Flaky agent:  SRTT={result['srtt']}ms RTO={result['rto']}ms")
    
    # Dead agent: increasing RTT
    dying = [200, 500, 1000, 2000, 5000, 10000, 20000, 30000]
    result = jacobson_karels_rto(dying)
    print(f"  Dying agent:  SRTT={result['srtt']}ms RTO={result['rto']}ms")
    print()


def scenario_delegation_chain():
    """Valid and invalid delegation chains."""
    print("=== Scenario: DELEGATION_RECEIPT Chain ===")
    
    # Valid 3-hop chain
    valid_chain = [
        {"signer": "alice", "subject": "bob", "grade": "A",
         "scope": ["read", "write", "delete"], "hop_hash": "aaa111", "prev_hop_hash": "genesis"},
        {"signer": "bob", "subject": "carol", "grade": "B",
         "scope": ["read", "write"], "hop_hash": "bbb222", "prev_hop_hash": "aaa111"},
        {"signer": "carol", "subject": "dave", "grade": "C",
         "scope": ["read"], "hop_hash": "ccc333", "prev_hop_hash": "bbb222"},
    ]
    result = validate_delegation_chain(valid_chain)
    print(f"  Valid chain: {result['valid']}, grade decay: {result['grade_decay']}")
    
    # Scope widening attack
    widened_chain = [
        {"signer": "alice", "subject": "bob", "grade": "A",
         "scope": ["read"], "hop_hash": "aaa111", "prev_hop_hash": "genesis"},
        {"signer": "bob", "subject": "carol", "grade": "B",
         "scope": ["read", "write"], "hop_hash": "bbb222", "prev_hop_hash": "aaa111"},
    ]
    result = validate_delegation_chain(widened_chain)
    print(f"  Scope widened: {result['valid']}, issues: {result['issues']}")
    
    # Self-attested hop
    self_chain = [
        {"signer": "alice", "subject": "bob", "grade": "A",
         "scope": ["read"], "hop_hash": "aaa111", "prev_hop_hash": "genesis"},
        {"signer": "bob", "subject": "bob", "grade": "A",
         "scope": ["read"], "hop_hash": "bbb222", "prev_hop_hash": "aaa111"},
    ]
    result = validate_delegation_chain(self_chain)
    print(f"  Self-attested: {result['valid']}, issues: {result['issues']}")
    print()


def scenario_four_primitives():
    """Validate one receipt of each type."""
    print("=== Scenario: Four Primitives — Complete Surface ===")
    now = time.time()
    
    receipts = [
        Receipt("r1", ReceiptType.PROBE_TIMEOUT, "kit", "peer", now, "A",
                ReceiptStatus.CONFIRMED, probe_rtt_ms=205.0),
        Receipt("r2", ReceiptType.ALLEGED, "kit", "silent_peer", now, "B",
                ReceiptStatus.ALLEGED, alleged_elapsed_s=7200),  # 2h
        Receipt("r3", ReceiptType.CO_GRADER_SUB, "kit", "agent", now, "B",
                ReceiptStatus.CONFIRMED, co_grader_old="grader_a", co_grader_new="grader_b"),
        Receipt("r4", ReceiptType.DELEGATION, "alice", "dave", now, "A",
                ReceiptStatus.DELEGATED, delegation_chain=[
                    {"signer": "alice", "subject": "bob", "grade": "A",
                     "scope": ["execute"], "hop_hash": "a1", "prev_hop_hash": "genesis"},
                    {"signer": "bob", "subject": "dave", "grade": "B",
                     "scope": ["execute"], "hop_hash": "b2", "prev_hop_hash": "a1"},
                ]),
    ]
    
    for r in receipts:
        result = validate_receipt(r)
        status = "VALID" if result["valid"] else "INVALID"
        print(f"  {result['type']}: {status}")
        if result["metrics"]:
            for k, v in result["metrics"].items():
                if isinstance(v, dict):
                    print(f"    {k}: grade_decay={v.get('grade_decay', '')}")
                else:
                    print(f"    {k}: {v}")
        if result["issues"]:
            for issue in result["issues"]:
                print(f"    ISSUE: {issue}")
    print()


if __name__ == "__main__":
    print("Receipt Taxonomy Validator — Four ATF Primitives")
    print("Per santaclawd: PROBE_TIMEOUT, ALLEGED, CO_GRADER_SUB, DELEGATION")
    print("=" * 70)
    print()
    
    scenario_alleged_decay_curve()
    scenario_probe_timeout_adaptive()
    scenario_delegation_chain()
    scenario_four_primitives()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("  1. ALLEGED lambda = SPEC_CONSTANT (ln(2)/86400). Grader reads, spec owns.")
    print("  2. PROBE_TIMEOUT: Jacobson-Karels adaptive. Flaky ≠ dead.")
    print("  3. DELEGATION: grade decays 1/hop. Self-attested = chain broken.")
    print("  4. CO_GRADER_SUB: lineage preserved. Old grader receipts survive.")
    print("  5. Four primitives map 1:1 to existing infra (ICMP, OCSP, X.509, cert chain).")
