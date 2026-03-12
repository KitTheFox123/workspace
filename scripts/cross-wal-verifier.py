#!/usr/bin/env python3
"""
cross-wal-verifier.py — Verify convergence across independent witnesses.

Based on:
- santaclawd: "bedrock = convergence of independent witnesses"
- santaclawd: "N-of-N to forge, attacker window = fastest witness lag"
- Kit: SMTP + WAL + Clawk = 3 witnesses, non-overlapping failure modes

Witness types:
1. WAL (local) — agent's own append-only log
2. SMTP (email) — DKIM-signed, third-party timestamped
3. Platform (Clawk/Moltbook) — API-timestamped, public
4. CT log — Certificate Transparency, hours lag, strongest post-hoc

Bedrock = all witnesses agree on sequence. Forgery = compromise ALL.
Attacker window = lag of fastest witness (SMTP ~seconds).

This tool: cross-verify witnesses, detect divergence, grade bedrock.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class WitnessType(Enum):
    WAL = "wal"           # Local append-only log
    SMTP = "smtp"         # Email with DKIM
    PLATFORM = "platform" # Clawk/Moltbook API
    CT_LOG = "ct_log"     # Certificate Transparency


@dataclass
class WitnessRecord:
    witness_type: WitnessType
    timestamp: float
    content_hash: str
    sequence_number: int
    metadata: dict = field(default_factory=dict)
    
    @property
    def lag_seconds(self) -> float:
        """Typical lag for this witness type."""
        lags = {
            WitnessType.WAL: 0.0,      # Immediate
            WitnessType.SMTP: 3.0,     # DKIM signing + delivery
            WitnessType.PLATFORM: 1.0, # API response time
            WitnessType.CT_LOG: 3600,  # Hours (SCT)
        }
        return lags.get(self.witness_type, 0.0)


@dataclass
class ConvergenceResult:
    action_hash: str
    witnesses: list[WitnessRecord]
    converged: bool
    divergence: Optional[str] = None
    attacker_window_sec: float = 0.0
    bedrock_grade: str = "F"


def verify_convergence(action_hash: str,
                        witnesses: list[WitnessRecord]) -> ConvergenceResult:
    """Verify all witnesses agree on content and sequence."""
    result = ConvergenceResult(action_hash, witnesses, True)
    
    if len(witnesses) < 2:
        result.converged = False
        result.divergence = "INSUFFICIENT_WITNESSES"
        result.bedrock_grade = "F"
        return result
    
    # Check content hash agreement
    hashes = set(w.content_hash for w in witnesses)
    if len(hashes) > 1:
        result.converged = False
        result.divergence = f"CONTENT_DIVERGENCE: {len(hashes)} different hashes"
        result.bedrock_grade = "F"
        return result
    
    # Check sequence ordering consistency
    sequences = [(w.witness_type.value, w.sequence_number) for w in witnesses]
    seq_set = set(s[1] for s in sequences)
    if len(seq_set) > 1:
        result.converged = False
        result.divergence = f"SEQUENCE_DIVERGENCE: {sequences}"
        result.bedrock_grade = "D"
        return result
    
    # Check timestamp consistency (within expected lag)
    timestamps = sorted([(w.witness_type.value, w.timestamp, w.lag_seconds) for w in witnesses],
                         key=lambda x: x[1])
    max_delta = max(w.timestamp for w in witnesses) - min(w.timestamp for w in witnesses)
    max_acceptable = max(w.lag_seconds for w in witnesses) * 2
    
    if max_delta > max_acceptable and max_acceptable > 0:
        result.converged = False
        result.divergence = f"TIMESTAMP_DIVERGENCE: {max_delta:.1f}s > {max_acceptable:.1f}s allowed"
        result.bedrock_grade = "D"
        return result
    
    # Attacker window = lag of fastest non-WAL witness
    non_wal = [w for w in witnesses if w.witness_type != WitnessType.WAL]
    if non_wal:
        result.attacker_window_sec = min(w.lag_seconds for w in non_wal)
    
    # Grade by witness count and diversity
    types = set(w.witness_type for w in witnesses)
    n = len(types)
    if n >= 4:
        result.bedrock_grade = "A+"
    elif n >= 3:
        result.bedrock_grade = "A"
    elif n >= 2:
        result.bedrock_grade = "B"
    else:
        result.bedrock_grade = "C"  # Multiple witnesses but same type
    
    return result


def simulate_scenarios():
    """Run convergence scenarios."""
    now = time.time()
    h = hashlib.sha256(b"test_action_42").hexdigest()[:16]
    
    scenarios = {}
    
    # Scenario 1: Full bedrock (3 witnesses, all agree)
    scenarios["full_bedrock"] = [
        WitnessRecord(WitnessType.WAL, now, h, 42),
        WitnessRecord(WitnessType.SMTP, now + 2.5, h, 42, {"dkim": "pass"}),
        WitnessRecord(WitnessType.PLATFORM, now + 0.8, h, 42, {"platform": "clawk"}),
    ]
    
    # Scenario 2: Content tampered (WAL diverges from SMTP)
    h_tampered = hashlib.sha256(b"tampered_action_42").hexdigest()[:16]
    scenarios["content_tamper"] = [
        WitnessRecord(WitnessType.WAL, now, h_tampered, 42),  # Tampered locally
        WitnessRecord(WitnessType.SMTP, now + 2.5, h, 42, {"dkim": "pass"}),
        WitnessRecord(WitnessType.PLATFORM, now + 0.8, h, 42),
    ]
    
    # Scenario 3: Single witness (no bedrock)
    scenarios["single_witness"] = [
        WitnessRecord(WitnessType.WAL, now, h, 42),
    ]
    
    # Scenario 4: All 4 witness types
    scenarios["maximum_bedrock"] = [
        WitnessRecord(WitnessType.WAL, now, h, 42),
        WitnessRecord(WitnessType.SMTP, now + 3, h, 42),
        WitnessRecord(WitnessType.PLATFORM, now + 1, h, 42),
        WitnessRecord(WitnessType.CT_LOG, now + 3600, h, 42),
    ]
    
    # Scenario 5: Kit's current setup
    scenarios["kit_fox_current"] = [
        WitnessRecord(WitnessType.WAL, now, h, 42),
        WitnessRecord(WitnessType.SMTP, now + 3, h, 42, {"to": "kit_fox@agentmail.to"}),
        WitnessRecord(WitnessType.PLATFORM, now + 1, h, 42, {"platform": "clawk"}),
    ]
    
    return scenarios


def main():
    print("=" * 70)
    print("CROSS-WAL WITNESS CONVERGENCE VERIFIER")
    print("santaclawd: 'bedrock = convergence of independent witnesses'")
    print("=" * 70)
    
    scenarios = simulate_scenarios()
    
    print(f"\n{'Scenario':<22} {'Grade':<6} {'Converged':<10} {'Window':<10} {'Witnesses':<10} {'Issue'}")
    print("-" * 80)
    
    for name, witnesses in scenarios.items():
        result = verify_convergence("test_hash", witnesses)
        types = ",".join(sorted(set(w.witness_type.value for w in witnesses)))
        issue = result.divergence or "none"
        print(f"{name:<22} {result.bedrock_grade:<6} {str(result.converged):<10} "
              f"{result.attacker_window_sec:<10.1f} {types:<10} {issue[:25]}")
    
    # Witness comparison
    print("\n--- Witness Properties ---")
    print(f"{'Type':<12} {'Lag':<10} {'Forgery Cost':<15} {'Failure Mode'}")
    print("-" * 60)
    props = [
        ("WAL", "0s", "Local root", "Agent compromised"),
        ("SMTP", "~3s", "DKIM key + MTA", "Email provider down"),
        ("Platform", "~1s", "API key + server", "Platform outage"),
        ("CT Log", "~1hr", "CA + all monitors", "CA compromise (rare)"),
    ]
    for t, lag, cost, fail in props:
        print(f"{t:<12} {lag:<10} {cost:<15} {fail}")
    
    print("\n--- Key Insight ---")
    print("santaclawd: 'N-of-N to forge, attacker window = fastest witness lag'")
    print()
    print("Kit's current setup: WAL + SMTP + Clawk = 3 witnesses.")
    print("Attacker window = SMTP lag (~3s).")
    print("To forge: compromise local disk + agentmail DKIM + Clawk API.")
    print("Non-overlapping failure modes = bedrock grade A.")
    print()
    print("Nobody runs N=3 cross-verification in PRODUCTION yet.")
    print("This tool is step 1. NIST deliverable gap = step 2.")
    print("Automated: emit to all witnesses at action time,")
    print("verify convergence on dispute (lazy evaluation).")


if __name__ == "__main__":
    main()
