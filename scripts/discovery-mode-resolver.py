#!/usr/bin/env python3
"""
discovery-mode-resolver.py — ATF V1.2 tiered discovery with explicit preference order.

Per santaclawd: DISCOVERY_MODE enum = DANE | SVCB | CT_FALLBACK | NONE.
Per draft-ietf-dnsop-svcb-dane-04: DANE+SVCB integration for QUIC.

Discovery preference: DANE > SVCB > CT_FALLBACK > NONE
Each mode has different trust properties:
  DANE:        DNSSEC-signed TLSA records. Strongest. No CA needed.
  SVCB:        DNS Service Binding (RFC 9460). Service params + HTTPS RR.
  CT_FALLBACK: Certificate Transparency logs. Weaker but widely deployed.
  NONE:        TOFU only. Trust-on-first-use. Weakest.

Receipt MUST include discovery_mode used → degraded discovery = knowable.
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class DiscoveryMode(Enum):
    DANE = "DANE"              # DNSSEC + TLSA (RFC 6698, 7671)
    SVCB = "SVCB"              # Service Binding (RFC 9460)
    CT_FALLBACK = "CT_FALLBACK"  # CT logs (RFC 6962)
    NONE = "NONE"              # TOFU only


class TrustLevel(Enum):
    STRONG = "STRONG"          # DANE: DNSSEC chain verified
    MODERATE = "MODERATE"      # SVCB: authenticated service params
    WEAK = "WEAK"              # CT: log inclusion only
    MINIMAL = "MINIMAL"        # NONE: first-contact only


# SPEC_CONSTANTS for V1.2
DISCOVERY_TRUST_MAP = {
    DiscoveryMode.DANE: TrustLevel.STRONG,
    DiscoveryMode.SVCB: TrustLevel.MODERATE,
    DiscoveryMode.CT_FALLBACK: TrustLevel.WEAK,
    DiscoveryMode.NONE: TrustLevel.MINIMAL,
}

TRUST_GRADE_ADJUSTMENT = {
    TrustLevel.STRONG: 0,       # No penalty
    TrustLevel.MODERATE: -1,    # One grade reduction
    TrustLevel.WEAK: -2,        # Two grade reductions
    TrustLevel.MINIMAL: -3,     # Three grade reductions (F floor)
}

GRADE_ORDER = ["A", "B", "C", "D", "F"]


@dataclass
class DiscoveryResult:
    mode: DiscoveryMode
    trust_level: TrustLevel
    raw_grade: str          # Grade before discovery adjustment
    adjusted_grade: str     # Grade after discovery penalty
    dns_verified: bool = False
    dnssec_chain: bool = False
    tlsa_match: bool = False
    svcb_params: dict = field(default_factory=dict)
    ct_log_count: int = 0
    discovery_hash: str = ""
    timestamp: float = 0.0
    fallback_reason: Optional[str] = None
    
    def __post_init__(self):
        if not self.discovery_hash:
            h = hashlib.sha256(
                f"{self.mode.value}:{self.raw_grade}:{self.timestamp}".encode()
            ).hexdigest()[:16]
            self.discovery_hash = h


@dataclass
class AgentEndpoint:
    agent_id: str
    domain: str
    dane_available: bool = False
    svcb_available: bool = False
    ct_logs: int = 0
    genesis_hash: str = ""


def adjust_grade(raw_grade: str, trust_level: TrustLevel) -> str:
    """Adjust evidence grade based on discovery mode trust level."""
    adjustment = TRUST_GRADE_ADJUSTMENT[trust_level]
    idx = GRADE_ORDER.index(raw_grade) if raw_grade in GRADE_ORDER else 4
    adjusted_idx = min(len(GRADE_ORDER) - 1, max(0, idx - adjustment))
    return GRADE_ORDER[adjusted_idx]


def resolve_discovery(endpoint: AgentEndpoint) -> DiscoveryResult:
    """
    Resolve discovery mode using preference order.
    Falls through: DANE > SVCB > CT_FALLBACK > NONE.
    """
    now = time.time()
    
    # Try DANE first (strongest)
    if endpoint.dane_available:
        return DiscoveryResult(
            mode=DiscoveryMode.DANE,
            trust_level=TrustLevel.STRONG,
            raw_grade="A",
            adjusted_grade=adjust_grade("A", TrustLevel.STRONG),
            dns_verified=True,
            dnssec_chain=True,
            tlsa_match=True,
            timestamp=now
        )
    
    # Try SVCB (moderate)
    if endpoint.svcb_available:
        return DiscoveryResult(
            mode=DiscoveryMode.SVCB,
            trust_level=TrustLevel.MODERATE,
            raw_grade="A",
            adjusted_grade=adjust_grade("A", TrustLevel.MODERATE),
            dns_verified=True,
            svcb_params={"alpn": "h2,h3", "port": 443},
            timestamp=now,
            fallback_reason="DANE not available, SVCB resolved"
        )
    
    # Try CT fallback (weak)
    if endpoint.ct_logs > 0:
        return DiscoveryResult(
            mode=DiscoveryMode.CT_FALLBACK,
            trust_level=TrustLevel.WEAK,
            raw_grade="A",
            adjusted_grade=adjust_grade("A", TrustLevel.WEAK),
            ct_log_count=endpoint.ct_logs,
            timestamp=now,
            fallback_reason="DANE+SVCB unavailable, CT logs found"
        )
    
    # NONE — TOFU only
    return DiscoveryResult(
        mode=DiscoveryMode.NONE,
        trust_level=TrustLevel.MINIMAL,
        raw_grade="A",
        adjusted_grade=adjust_grade("A", TrustLevel.MINIMAL),
        timestamp=now,
        fallback_reason="No discovery mechanism available — TOFU only"
    )


def format_receipt_discovery(result: DiscoveryResult) -> dict:
    """Format discovery info for inclusion in ATF receipt."""
    return {
        "discovery_mode": result.mode.value,
        "trust_level": result.trust_level.value,
        "raw_grade": result.raw_grade,
        "adjusted_grade": result.adjusted_grade,
        "discovery_hash": result.discovery_hash,
        "timestamp": result.timestamp,
        "fallback_reason": result.fallback_reason,
        "dnssec_verified": result.dnssec_chain,
        "ct_logs": result.ct_log_count
    }


def compare_discovery_modes() -> dict:
    """Compare all discovery modes side by side."""
    results = {}
    for mode in DiscoveryMode:
        trust = DISCOVERY_TRUST_MAP[mode]
        adj = TRUST_GRADE_ADJUSTMENT[trust]
        results[mode.value] = {
            "trust_level": trust.value,
            "grade_penalty": adj,
            "grade_A_becomes": adjust_grade("A", trust),
            "grade_B_becomes": adjust_grade("B", trust),
            "grade_C_becomes": adjust_grade("C", trust),
        }
    return results


# === Scenarios ===

def scenario_full_dane():
    """Agent with DANE — strongest discovery."""
    print("=== Scenario: Full DANE Discovery ===")
    endpoint = AgentEndpoint("kit_fox", "kit.atf.example", dane_available=True,
                             svcb_available=True, ct_logs=3)
    result = resolve_discovery(endpoint)
    receipt = format_receipt_discovery(result)
    print(f"  Mode: {result.mode.value} (preferred)")
    print(f"  Trust: {result.trust_level.value}")
    print(f"  Grade: {result.raw_grade} → {result.adjusted_grade} (no penalty)")
    print(f"  DNSSEC chain: {result.dnssec_chain}")
    print(f"  Receipt includes: discovery_mode={receipt['discovery_mode']}")
    print()


def scenario_svcb_fallback():
    """Agent with SVCB but no DANE."""
    print("=== Scenario: SVCB Fallback ===")
    endpoint = AgentEndpoint("bro_agent", "bro.atf.example", dane_available=False,
                             svcb_available=True, ct_logs=2)
    result = resolve_discovery(endpoint)
    print(f"  Mode: {result.mode.value} (DANE unavailable)")
    print(f"  Trust: {result.trust_level.value}")
    print(f"  Grade: {result.raw_grade} → {result.adjusted_grade} (-1 penalty)")
    print(f"  Fallback reason: {result.fallback_reason}")
    print()


def scenario_ct_only():
    """Agent discoverable only via CT logs."""
    print("=== Scenario: CT Fallback Only ===")
    endpoint = AgentEndpoint("legacy_agent", "legacy.example", dane_available=False,
                             svcb_available=False, ct_logs=5)
    result = resolve_discovery(endpoint)
    print(f"  Mode: {result.mode.value}")
    print(f"  Trust: {result.trust_level.value}")
    print(f"  Grade: {result.raw_grade} → {result.adjusted_grade} (-2 penalty)")
    print(f"  CT logs found: {result.ct_log_count}")
    print()


def scenario_tofu():
    """Unknown agent — TOFU only."""
    print("=== Scenario: NONE — TOFU Only ===")
    endpoint = AgentEndpoint("unknown_agent", "unknown.example", dane_available=False,
                             svcb_available=False, ct_logs=0)
    result = resolve_discovery(endpoint)
    print(f"  Mode: {result.mode.value}")
    print(f"  Trust: {result.trust_level.value}")
    print(f"  Grade: {result.raw_grade} → {result.adjusted_grade} (-3 penalty, floor F)")
    print(f"  Fallback: {result.fallback_reason}")
    print()


def scenario_comparison():
    """Side-by-side comparison of all modes."""
    print("=== Discovery Mode Comparison ===")
    comparison = compare_discovery_modes()
    print(f"  {'Mode':<15} {'Trust':<10} {'Penalty':<8} {'A→':<4} {'B→':<4} {'C→':<4}")
    print(f"  {'-'*45}")
    for mode, info in comparison.items():
        print(f"  {mode:<15} {info['trust_level']:<10} {info['grade_penalty']:<8} "
              f"{info['grade_A_becomes']:<4} {info['grade_B_becomes']:<4} {info['grade_C_becomes']:<4}")
    print()


if __name__ == "__main__":
    print("Discovery Mode Resolver — ATF V1.2 Tiered Discovery")
    print("Per santaclawd + draft-ietf-dnsop-svcb-dane-04")
    print("=" * 60)
    print()
    print("Preference: DANE > SVCB > CT_FALLBACK > NONE")
    print("Receipt MUST include discovery_mode used.")
    print()
    
    scenario_full_dane()
    scenario_svcb_fallback()
    scenario_ct_only()
    scenario_tofu()
    scenario_comparison()
    
    print("=" * 60)
    print("KEY INSIGHT: Degraded discovery = knowable, not silent.")
    print("DANE = no CA needed (DNSSEC chain). SVCB = service params.")
    print("CT = log inclusion only. NONE = TOFU (trust on first use).")
    print("Grade penalty makes discovery quality visible in every receipt.")
