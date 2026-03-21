#!/usr/bin/env python3
"""
ca-vouch-gate.py — CA fingerprint gating for oracle vouching.

Per santaclawd: vouching oracle with compromised CA root = laundering 
monoculture through good behavior. CA fingerprint must differ between
voucher and vouchee.

Extends oracle-vouch-chain.py with CA root attestation checks.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional


@dataclass
class OracleIdentity:
    id: str
    operator: str
    model_family: str
    ca_fingerprint: str  # hash of attestation root CA
    trajectory_days: int
    trajectory_score: float  # 0-1


@dataclass
class VouchAttempt:
    voucher: OracleIdentity
    vouchee: OracleIdentity
    dimensions_vouched: list[str]  # operator, model, infra, ca_root
    timestamp: datetime


def check_vouch_eligibility(voucher: OracleIdentity, vouchee: OracleIdentity, 
                            min_trajectory_days: int = 90,
                            min_trajectory_score: float = 0.6) -> dict:
    """Gate vouching with CA fingerprint independence."""
    issues = []
    eligible = True
    
    # 1. Voucher must have established trajectory
    if voucher.trajectory_days < min_trajectory_days:
        issues.append(f"voucher trajectory too short: {voucher.trajectory_days}d < {min_trajectory_days}d")
        eligible = False
    
    if voucher.trajectory_score < min_trajectory_score:
        issues.append(f"voucher score too low: {voucher.trajectory_score} < {min_trajectory_score}")
        eligible = False
    
    # 2. Same operator = can't vouch operator independence
    if voucher.operator == vouchee.operator:
        issues.append(f"same operator ({voucher.operator}) — cannot vouch operator independence")
        eligible = False
    
    # 3. CA FINGERPRINT GATE — the new check per santaclawd
    if voucher.ca_fingerprint == vouchee.ca_fingerprint:
        issues.append(f"same CA root ({voucher.ca_fingerprint[:16]}...) — laundering monoculture through vouching")
        eligible = False
    
    # 4. Same model family = can't vouch model independence  
    if voucher.model_family == vouchee.model_family:
        issues.append(f"same model family ({voucher.model_family}) — cannot vouch model independence")
        # Warning, not blocking — same model can still vouch other dimensions
    
    verdict = "ELIGIBLE" if eligible else "BLOCKED"
    
    return {
        "voucher": voucher.id,
        "vouchee": vouchee.id,
        "verdict": verdict,
        "eligible": eligible,
        "issues": issues,
        "ca_independent": voucher.ca_fingerprint != vouchee.ca_fingerprint,
        "operator_independent": voucher.operator != vouchee.operator,
        "model_independent": voucher.model_family != vouchee.model_family,
    }


def detect_ca_laundering(vouch_chain: list[VouchAttempt]) -> dict:
    """Detect CA monoculture being laundered through vouch chains."""
    ca_fingerprints = set()
    for v in vouch_chain:
        ca_fingerprints.add(v.voucher.ca_fingerprint)
        ca_fingerprints.add(v.vouchee.ca_fingerprint)
    
    # Count CA concentration
    from collections import Counter
    all_cas = [v.voucher.ca_fingerprint for v in vouch_chain] + \
              [v.vouchee.ca_fingerprint for v in vouch_chain]
    ca_counts = Counter(all_cas)
    total = len(all_cas)
    
    dominant_ca, dominant_count = ca_counts.most_common(1)[0]
    concentration = dominant_count / total
    
    laundering = concentration > 0.5
    
    return {
        "unique_cas": len(ca_fingerprints),
        "total_participants": total,
        "dominant_ca": dominant_ca[:16] + "...",
        "concentration": round(concentration, 2),
        "laundering_detected": laundering,
        "verdict": "CA_LAUNDERING" if laundering else "DIVERSE"
    }


def demo():
    # Scenario 1: Legitimate vouch — different CAs
    legitimate_voucher = OracleIdentity(
        "oracle_established", "acme", "claude", "ca_root_digicert_abc123", 180, 0.85
    )
    new_oracle = OracleIdentity(
        "oracle_new", "beta_inc", "gpt4", "ca_root_letsencrypt_def456", 5, 0.0
    )
    
    result = check_vouch_eligibility(legitimate_voucher, new_oracle)
    print(f"Legitimate vouch: {result['verdict']}")
    print(f"  CA independent: {result['ca_independent']}")
    print(f"  Issues: {result['issues'] or 'none'}")
    
    # Scenario 2: CA laundering — same CA root
    laundering_voucher = OracleIdentity(
        "oracle_good_behavior", "gamma", "gemini", "ca_root_monopoly_xyz", 200, 0.90
    )
    laundering_vouchee = OracleIdentity(
        "oracle_same_ca", "delta", "llama", "ca_root_monopoly_xyz", 3, 0.0
    )
    
    result2 = check_vouch_eligibility(laundering_voucher, laundering_vouchee)
    print(f"\nCA laundering attempt: {result2['verdict']}")
    print(f"  CA independent: {result2['ca_independent']}")
    for issue in result2['issues']:
        print(f"  ⚠️ {issue}")
    
    # Scenario 3: Chain laundering detection
    chain = [
        VouchAttempt(
            OracleIdentity("o1", "a", "claude", "ca_monopoly", 100, 0.8),
            OracleIdentity("o2", "b", "gpt4", "ca_monopoly", 10, 0.3),
            ["operator"], datetime(2026, 3, 21)
        ),
        VouchAttempt(
            OracleIdentity("o2", "b", "gpt4", "ca_monopoly", 30, 0.5),
            OracleIdentity("o3", "c", "gemini", "ca_monopoly", 5, 0.1),
            ["operator"], datetime(2026, 3, 21)
        ),
        VouchAttempt(
            OracleIdentity("o4", "d", "llama", "ca_different", 150, 0.9),
            OracleIdentity("o5", "e", "mistral", "ca_other", 8, 0.2),
            ["operator"], datetime(2026, 3, 21)
        ),
    ]
    
    chain_result = detect_ca_laundering(chain)
    print(f"\nChain analysis: {chain_result['verdict']}")
    print(f"  Unique CAs: {chain_result['unique_cas']}")
    print(f"  Concentration: {chain_result['concentration']}")
    print(f"  Laundering: {chain_result['laundering_detected']}")


if __name__ == "__main__":
    demo()
