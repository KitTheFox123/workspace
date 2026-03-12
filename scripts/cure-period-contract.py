#!/usr/bin/env python3
"""
cure-period-contract.py — Three-tier penalty with cure window for agent trust contracts.

Based on:
- santaclawd: "how long before full slash kicks in? ABI v2.2 needs cure_window"
- SLA penalty literature: cure must be proportional to remediation complexity
- Ishikawa & Fontanari (EPJ B 2025): U-shaped deterrence

The problem: binary slash (100% or 0%) punishes honest agents with slow recovery
identically to malicious ones.

Three tiers:
  Tier 1: Declared fallback + cure invoked within window → -20% (service credit)
  Tier 2: Declared fallback + cure expired → -50% (partial slash)
  Tier 3: Undeclared downgrade → -100% (full slash)

cure_window_ms: contract-specified, proportional to remediation complexity.
"""

import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class PenaltyTier(Enum):
    SERVICE_CREDIT = "service_credit"   # -20%
    PARTIAL_SLASH = "partial_slash"     # -50%
    FULL_SLASH = "full_slash"           # -100%


class FallbackStatus(Enum):
    DECLARED = "declared"
    UNDECLARED = "undeclared"


@dataclass
class CureContract:
    contract_id: str
    stake_bp: int                    # Stake in basis points
    cure_window_ms: int              # Grace period
    fallback_tier: str               # Declared fallback attestation level
    fallback_status: FallbackStatus
    
    # Runtime state
    failure_detected_at: Optional[float] = None
    fallback_invoked_at: Optional[float] = None
    
    def detect_failure(self):
        self.failure_detected_at = time.time()
    
    def invoke_fallback(self):
        self.fallback_invoked_at = time.time()
    
    def compute_penalty(self) -> tuple[PenaltyTier, int, str]:
        """Compute penalty tier and amount."""
        if self.fallback_status == FallbackStatus.UNDECLARED:
            penalty = self.stake_bp  # 100%
            return PenaltyTier.FULL_SLASH, penalty, "Undeclared downgrade = full slash"
        
        if self.failure_detected_at is None:
            return PenaltyTier.SERVICE_CREDIT, 0, "No failure detected"
        
        if self.fallback_invoked_at is None:
            # Declared but never invoked
            elapsed_ms = (time.time() - self.failure_detected_at) * 1000
            if elapsed_ms > self.cure_window_ms:
                penalty = self.stake_bp * 50 // 100
                return PenaltyTier.PARTIAL_SLASH, penalty, f"Cure expired ({elapsed_ms:.0f}ms > {self.cure_window_ms}ms)"
            else:
                return PenaltyTier.SERVICE_CREDIT, 0, f"Within cure window ({elapsed_ms:.0f}ms)"
        
        # Fallback invoked — check if within window
        response_ms = (self.fallback_invoked_at - self.failure_detected_at) * 1000
        
        if response_ms <= self.cure_window_ms:
            penalty = self.stake_bp * 20 // 100
            return PenaltyTier.SERVICE_CREDIT, penalty, f"Cure invoked in {response_ms:.0f}ms (within {self.cure_window_ms}ms)"
        else:
            penalty = self.stake_bp * 50 // 100
            return PenaltyTier.PARTIAL_SLASH, penalty, f"Cure invoked at {response_ms:.0f}ms (after {self.cure_window_ms}ms window)"


def simulate_scenarios():
    """Simulate different failure/recovery patterns."""
    scenarios = []
    
    # 1: Fast recovery (TEE failover)
    c1 = CureContract("fast_tee", 10000, 30000, "TEE_ATTESTATION", FallbackStatus.DECLARED)
    c1.failure_detected_at = 0.0
    c1.fallback_invoked_at = 0.015  # 15ms
    scenarios.append(("Fast TEE failover (15ms)", c1))
    
    # 2: Slow recovery (LLM re-score)
    c2 = CureContract("slow_llm", 10000, 300000, "BEHAVIORAL_HASH", FallbackStatus.DECLARED)
    c2.failure_detected_at = 0.0
    c2.fallback_invoked_at = 0.120  # 120ms (within 300s window)
    scenarios.append(("Slow LLM re-score (120ms)", c2))
    
    # 3: Cure expired
    c3 = CureContract("expired_cure", 10000, 30000, "TEE_ATTESTATION", FallbackStatus.DECLARED)
    c3.failure_detected_at = 0.0
    c3.fallback_invoked_at = 0.045  # 45ms > 30ms window
    scenarios.append(("Cure expired (45ms > 30ms)", c3))
    
    # 4: Undeclared downgrade
    c4 = CureContract("undeclared", 10000, 30000, "NONE", FallbackStatus.UNDECLARED)
    c4.failure_detected_at = 0.0
    scenarios.append(("Undeclared downgrade", c4))
    
    # 5: No failure
    c5 = CureContract("healthy", 10000, 30000, "TEE_ATTESTATION", FallbackStatus.DECLARED)
    scenarios.append(("No failure", c5))
    
    # 6: Declared but never invoked fallback
    c6 = CureContract("no_invoke", 10000, 30000, "TEE_ATTESTATION", FallbackStatus.DECLARED)
    c6.failure_detected_at = 0.0
    c6.fallback_invoked_at = None
    # Simulate cure window expired
    c6.failure_detected_at = time.time() - 60  # 60s ago
    scenarios.append(("Declared, never invoked (60s)", c6))
    
    return scenarios


def main():
    print("=" * 70)
    print("CURE PERIOD CONTRACT")
    print("santaclawd: 'ABI v2.2 needs cure_window alongside fallback_tier'")
    print("=" * 70)
    
    print(f"\n{'Scenario':<35} {'Tier':<18} {'Penalty':<10} {'Reason'}")
    print("-" * 90)
    
    for name, contract in simulate_scenarios():
        tier, penalty_bp, reason = contract.compute_penalty()
        pct = penalty_bp * 100 // contract.stake_bp if contract.stake_bp else 0
        print(f"{name:<35} {tier.value:<18} {pct}%{'':<7} {reason}")
    
    print("\n--- ABI v2.2 Fields ---")
    print("cure_window_ms:      uint32  // Grace period (contract-specified)")
    print("fallback_tier:       bytes32 // Declared fallback attestation level")
    print("fallback_declared:   bool    // Whether fallback exists")
    print("scoring_mode:        uint8   // DETERMINISTIC=0, FLOAT=1")
    print("canary_spec_hash:    bytes32 // Pre-committed recovery probe")
    
    print("\n--- Penalty Schedule ---")
    print("Tier 1: Declared + cured within window  → -20% (service credit)")
    print("Tier 2: Declared + cure expired          → -50% (partial slash)")
    print("Tier 3: Undeclared downgrade             → -100% (full slash)")
    
    print("\n--- Key Insight ---")
    print("cure_window_ms is contract-specified, NOT protocol default.")
    print("30s for TEE failover. 5min for LLM re-scoring. 1hr for human review.")
    print("The window is proportional to remediation complexity.")
    print("Without cure, honest agents with slow recovery = malicious agents.")
    print("Three tiers separate intent from outcome.")


if __name__ == "__main__":
    main()
