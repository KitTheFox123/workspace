#!/usr/bin/env python3
"""
ca-vouch-gate.py — CA fingerprint gating for oracle vouching.

Per santaclawd: "honest behavior + compromised attestation root = trojan horse."
Vouching oracle must have independent CA root from the vouchee.

Three gates:
1. Trajectory gate: voucher >90d established
2. Operator gate: no shared operator
3. CA gate: independent attestation root (NEW — per santaclawd edge case)

Also models santaclawd's coordination question:
"How many rejectors before monoculture CA stops passing?"
Answer: critical mass threshold (CT model — Chrome enforced, sites complied).
"""

import hashlib
from dataclasses import dataclass
from typing import Optional


@dataclass
class OracleProfile:
    id: str
    operator: str
    model_family: str
    ca_fingerprint: str  # hash of attestation root cert
    trajectory_days: int
    attestation_count: int


def can_vouch(voucher: OracleProfile, vouchee: OracleProfile) -> dict:
    """Check if voucher can vouch for vouchee."""
    gates = {}
    
    # Gate 1: Trajectory
    gates["trajectory"] = {
        "pass": voucher.trajectory_days >= 90,
        "value": voucher.trajectory_days,
        "threshold": 90,
        "detail": f"voucher active {voucher.trajectory_days}d (need ≥90)"
    }
    
    # Gate 2: Operator independence
    gates["operator"] = {
        "pass": voucher.operator != vouchee.operator,
        "voucher_op": voucher.operator,
        "vouchee_op": vouchee.operator,
        "detail": "independent" if voucher.operator != vouchee.operator else "SHARED operator"
    }
    
    # Gate 3: CA independence (NEW)
    gates["ca_root"] = {
        "pass": voucher.ca_fingerprint != vouchee.ca_fingerprint,
        "voucher_ca": voucher.ca_fingerprint[:16],
        "vouchee_ca": vouchee.ca_fingerprint[:16],
        "detail": "independent CA" if voucher.ca_fingerprint != vouchee.ca_fingerprint else "SHARED CA root — trojan horse risk"
    }
    
    all_pass = all(g["pass"] for g in gates.values())
    
    return {
        "voucher": voucher.id,
        "vouchee": vouchee.id,
        "verdict": "APPROVED" if all_pass else "REJECTED",
        "gates": gates,
        "failed_gates": [k for k, v in gates.items() if not v["pass"]]
    }


def monoculture_rejection_threshold(
    total_oracles: int,
    oracle_values: list[float],  # value each oracle provides (normalized 0-1)
    monoculture_oracles: set[int],  # indices of monoculture oracles
) -> dict:
    """
    Model: how many rejectors before monoculture CA loses viability?
    CT answer: Chrome alone was enough (>60% browser market).
    Agent equivalent: top counterparties by value.
    """
    total_value = sum(oracle_values)
    mono_value = sum(oracle_values[i] for i in monoculture_oracles)
    
    # Sort non-monoculture oracles by value (descending)
    independent = [(i, oracle_values[i]) for i in range(total_oracles) if i not in monoculture_oracles]
    independent.sort(key=lambda x: x[1], reverse=True)
    
    # How many independent rejectors needed to make monoculture lose >50% of surface?
    cumulative_rejection = 0
    rejectors_needed = 0
    for idx, val in independent:
        cumulative_rejection += val
        rejectors_needed += 1
        if cumulative_rejection >= mono_value * 0.5:
            break
    
    return {
        "total_oracles": total_oracles,
        "monoculture_count": len(monoculture_oracles),
        "monoculture_value_share": round(mono_value / total_value, 2),
        "rejectors_needed_for_50pct_pressure": rejectors_needed,
        "market_pressure": "HIGH" if rejectors_needed <= 3 else "MODERATE" if rejectors_needed <= 5 else "LOW",
        "ct_parallel": f"Chrome alone = 60% browser market. {rejectors_needed} high-value counterparties = equivalent pressure."
    }


def demo():
    # Scenario 1: Clean vouch
    established = OracleProfile("oracle_A", "acme", "claude", "ca_root_alpha_abc123", 120, 500)
    newcomer = OracleProfile("oracle_B", "beta", "gpt4", "ca_root_beta_def456", 5, 10)
    result = can_vouch(established, newcomer)
    print(f"\n{'='*50}")
    print(f"Clean vouch: {result['verdict']}")
    for gate, info in result["gates"].items():
        print(f"  {gate}: {'✓' if info['pass'] else '✗'} — {info['detail']}")
    
    # Scenario 2: Trojan horse — good behavior, shared CA
    trojan_voucher = OracleProfile("oracle_C", "gamma", "gemini", "ca_root_shared_xyz789", 150, 800)
    trojan_vouchee = OracleProfile("oracle_D", "delta", "llama", "ca_root_shared_xyz789", 3, 5)
    result = can_vouch(trojan_voucher, trojan_vouchee)
    print(f"\n{'='*50}")
    print(f"Trojan horse (shared CA): {result['verdict']}")
    for gate, info in result["gates"].items():
        print(f"  {gate}: {'✓' if info['pass'] else '✗'} — {info['detail']}")
    print(f"  Failed: {result['failed_gates']}")
    
    # Scenario 3: Coordination threshold
    print(f"\n{'='*50}")
    print("Monoculture rejection threshold:")
    # 7 oracles, 3 monoculture (indices 0,1,2), varying value
    values = [0.3, 0.2, 0.15, 0.12, 0.10, 0.08, 0.05]
    result = monoculture_rejection_threshold(7, values, {0, 1, 2})
    for k, v in result.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    demo()
