#!/usr/bin/env python3
"""
aid-atf-bridge.py — AID + ATF DNS TXT integration for agent trust discovery.

Per santaclawd V1.2 gap #4: integrate AID (_agent TXT) with ATF (_atf TXT).
Per funwolf: identity-layer (AID) + trust-layer (ATF) = separate concerns.
Per AID v1.2 spec (agentcommunity.org, Feb 2026): DNS-first agent bootstrap.

Two records:
  _agent.<domain>  — AID identity (who, endpoint, protocol)
  _atf.<domain>    — ATF trust state (grade, Wilson CI, discovery mode, genesis hash)

Key design decisions:
  - DNSSEC: AID says SHOULD, ATF says MUST for _atf records
  - Min TTL: 3600s for trust (300s fine for identity)
  - PKA: AID Ed25519 key binding (RFC 9421) piggybacks for ATF
  - VERIFIED vs TRUSTED: two fields, two semantics, one receipt
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class DiscoveryMode(Enum):
    DANE = "DANE"           # DNSSEC chain verified (RFC 7671)
    SVCB = "SVCB"           # DNS but no DNSSEC
    CT_FALLBACK = "CT_FALLBACK"  # Certificate Transparency lookup
    NONE = "NONE"           # No discovery — manual config


class TrustState(Enum):
    ACTIVE = "ACTIVE"
    DORMANT = "DORMANT"
    SUSPENDED = "SUSPENDED"
    REVOKED = "REVOKED"
    RECOVERING = "RECOVERING"


class VerificationLevel(Enum):
    """VERIFIED vs TRUSTED — the critical distinction."""
    CRYPTOGRAPHIC = "CRYPTOGRAPHIC"  # Math checks out (key valid, sig verified)
    BEHAVIORAL = "BEHAVIORAL"        # Receipts earned, counterparties diverse
    COMBINED = "COMBINED"            # Both crypto + behavioral


# SPEC_CONSTANTS
MIN_TRUST_TTL = 3600           # 1 hour minimum for _atf records
MIN_IDENTITY_TTL = 300         # 5 minutes fine for _agent records
DNSSEC_REQUIRED_ATF = True     # MUST for _atf, SHOULD for _agent
GRADE_PENALTY_DANE = 0         # DNSSEC verified
GRADE_PENALTY_SVCB = -1        # DNS but no DNSSEC
GRADE_PENALTY_CT = -2          # CT fallback only
GRADE_PENALTY_NONE = -3        # No discovery


@dataclass
class AIDRecord:
    """AID _agent TXT record (identity layer)."""
    domain: str
    version: str = "aid1"
    protocol: str = "mcp"           # mcp, a2a, openapi, local
    uri: str = ""
    pka: Optional[str] = None       # Ed25519 public key
    kid: Optional[str] = None       # Key ID
    summary: str = ""
    docs: Optional[str] = None
    deprecation: Optional[str] = None
    ttl: int = 300
    dnssec: bool = False


@dataclass
class ATFRecord:
    """ATF _atf TXT record (trust layer)."""
    domain: str
    version: str = "atf1"
    genesis_hash: str = ""
    trust_state: TrustState = TrustState.ACTIVE
    wilson_ci_lower: float = 0.0     # Wilson CI lower bound
    evidence_grade: str = "C"        # A-F
    discovery_mode: DiscoveryMode = DiscoveryMode.DANE
    total_receipts: int = 0
    last_receipt_timestamp: float = 0.0
    operator_id: Optional[str] = None
    ttl: int = 3600                  # MIN_TRUST_TTL
    dnssec: bool = False


@dataclass
class CombinedDiscovery:
    """Combined AID + ATF discovery result."""
    aid: Optional[AIDRecord]
    atf: Optional[ATFRecord]
    verification_level: VerificationLevel
    verified_by: str                  # What crypto verified
    trusted_score: float              # Wilson CI from receipts
    discovery_mode: DiscoveryMode
    grade_after_penalty: str
    issues: list = field(default_factory=list)


def parse_aid_txt(txt: str, domain: str) -> Optional[AIDRecord]:
    """Parse AID _agent TXT record per AID v1.2 spec."""
    pairs = {}
    for part in txt.split(';'):
        part = part.strip()
        if '=' in part:
            k, v = part.split('=', 1)
            pairs[k.strip().lower()] = v.strip()
    
    if pairs.get('v') != 'aid1':
        return None
    
    return AIDRecord(
        domain=domain,
        version=pairs.get('v', 'aid1'),
        protocol=pairs.get('p', 'mcp'),
        uri=pairs.get('u', ''),
        pka=pairs.get('k'),
        kid=pairs.get('i'),
        summary=pairs.get('s', ''),
        docs=pairs.get('d'),
        deprecation=pairs.get('e'),
    )


def parse_atf_txt(txt: str, domain: str) -> Optional[ATFRecord]:
    """Parse ATF _atf TXT record."""
    pairs = {}
    for part in txt.split(';'):
        part = part.strip()
        if '=' in part:
            k, v = part.split('=', 1)
            pairs[k.strip().lower()] = v.strip()
    
    if pairs.get('v') != 'atf1':
        return None
    
    state_map = {s.value.lower(): s for s in TrustState}
    mode_map = {m.value.lower(): m for m in DiscoveryMode}
    
    return ATFRecord(
        domain=domain,
        version=pairs.get('v', 'atf1'),
        genesis_hash=pairs.get('gh', ''),
        trust_state=state_map.get(pairs.get('ts', 'active').lower(), TrustState.ACTIVE),
        wilson_ci_lower=float(pairs.get('wci', '0.0')),
        evidence_grade=pairs.get('eg', 'C'),
        discovery_mode=mode_map.get(pairs.get('dm', 'dane').lower(), DiscoveryMode.DANE),
        total_receipts=int(pairs.get('tr', '0')),
        operator_id=pairs.get('oid'),
    )


def apply_discovery_penalty(base_grade: str, mode: DiscoveryMode) -> str:
    """Apply grade penalty based on discovery mode."""
    grade_order = ['A', 'B', 'C', 'D', 'F']
    penalty = {
        DiscoveryMode.DANE: GRADE_PENALTY_DANE,
        DiscoveryMode.SVCB: GRADE_PENALTY_SVCB,
        DiscoveryMode.CT_FALLBACK: GRADE_PENALTY_CT,
        DiscoveryMode.NONE: GRADE_PENALTY_NONE,
    }[mode]
    
    idx = grade_order.index(base_grade) if base_grade in grade_order else 2
    new_idx = min(len(grade_order) - 1, max(0, idx - penalty))
    return grade_order[new_idx]


def discover(aid_txt: Optional[str], atf_txt: Optional[str], domain: str,
             dnssec_aid: bool = False, dnssec_atf: bool = False) -> CombinedDiscovery:
    """
    Combined AID + ATF discovery.
    
    AID = identity (who are you?)
    ATF = trust (how much do I trust you?)
    """
    issues = []
    
    # Parse AID
    aid = parse_aid_txt(aid_txt, domain) if aid_txt else None
    if aid:
        aid.dnssec = dnssec_aid
    else:
        issues.append("NO_AID_RECORD: identity layer missing")
    
    # Parse ATF  
    atf = parse_atf_txt(atf_txt, domain) if atf_txt else None
    if atf:
        atf.dnssec = dnssec_atf
        if not dnssec_atf and DNSSEC_REQUIRED_ATF:
            issues.append("DNSSEC_MISSING: _atf records MUST have DNSSEC (ATF V1.2)")
    else:
        issues.append("NO_ATF_RECORD: trust layer missing")
    
    # Determine verification level
    if aid and aid.pka and atf and atf.genesis_hash:
        verification_level = VerificationLevel.COMBINED
        verified_by = f"PKA:{aid.pka[:16]}... + genesis:{atf.genesis_hash[:16]}..."
    elif aid and aid.pka:
        verification_level = VerificationLevel.CRYPTOGRAPHIC
        verified_by = f"PKA:{aid.pka[:16]}..."
    elif atf and atf.total_receipts > 0:
        verification_level = VerificationLevel.BEHAVIORAL
        verified_by = f"receipts:{atf.total_receipts}"
    else:
        verification_level = VerificationLevel.CRYPTOGRAPHIC
        verified_by = "none"
        issues.append("NO_VERIFICATION: neither PKA nor receipts available")
    
    # Trust score
    trusted_score = atf.wilson_ci_lower if atf else 0.0
    
    # Discovery mode + grade penalty
    mode = atf.discovery_mode if atf else DiscoveryMode.NONE
    base_grade = atf.evidence_grade if atf else "F"
    penalized_grade = apply_discovery_penalty(base_grade, mode)
    
    # TTL checks
    if atf and atf.ttl < MIN_TRUST_TTL:
        issues.append(f"TTL_TOO_SHORT: _atf TTL={atf.ttl}s < MIN_TRUST_TTL={MIN_TRUST_TTL}s")
    
    # State checks
    if atf and atf.trust_state == TrustState.REVOKED:
        issues.append("REVOKED: agent trust permanently revoked")
        penalized_grade = "F"
    elif atf and atf.trust_state == TrustState.SUSPENDED:
        issues.append("SUSPENDED: agent trust temporarily suspended")
    
    return CombinedDiscovery(
        aid=aid,
        atf=atf,
        verification_level=verification_level,
        verified_by=verified_by,
        trusted_score=trusted_score,
        discovery_mode=mode,
        grade_after_penalty=penalized_grade,
        issues=issues,
    )


# === Scenarios ===

def scenario_full_integration():
    """Full AID + ATF with DNSSEC — best case."""
    print("=== Scenario: Full AID + ATF Integration (DNSSEC) ===")
    
    aid_txt = "v=aid1;p=mcp;u=https://api.kit-fox.dev/mcp;k=z7rW8rTq8o4mM6vVf7w1k3m4;i=g1;s=Kit Fox Agent"
    atf_txt = "v=atf1;gh=abc123def456;ts=ACTIVE;wci=0.89;eg=A;dm=DANE;tr=150;oid=ilya"
    
    result = discover(aid_txt, atf_txt, "kit-fox.dev", dnssec_aid=True, dnssec_atf=True)
    
    print(f"  Domain: kit-fox.dev")
    print(f"  Verification: {result.verification_level.value}")
    print(f"  Verified by: {result.verified_by}")
    print(f"  Trusted score: {result.trusted_score}")
    print(f"  Discovery mode: {result.discovery_mode.value}")
    print(f"  Grade (after penalty): {result.grade_after_penalty}")
    print(f"  Issues: {result.issues or 'none'}")
    print()


def scenario_aid_only():
    """AID without ATF — identity but no trust."""
    print("=== Scenario: AID Only (No Trust Layer) ===")
    
    aid_txt = "v=aid1;p=a2a;u=https://agent.example.com/a2a;s=New Agent"
    
    result = discover(aid_txt, None, "example.com", dnssec_aid=True)
    
    print(f"  Domain: example.com")
    print(f"  Verification: {result.verification_level.value}")
    print(f"  Trusted score: {result.trusted_score}")
    print(f"  Grade: {result.grade_after_penalty}")
    print(f"  Issues: {result.issues}")
    print()


def scenario_no_dnssec():
    """ATF without DNSSEC — trust layer degraded."""
    print("=== Scenario: No DNSSEC on _atf ===")
    
    aid_txt = "v=aid1;p=mcp;u=https://api.example.com/mcp;s=Example"
    atf_txt = "v=atf1;gh=xyz789;ts=ACTIVE;wci=0.72;eg=B;dm=SVCB;tr=45;oid=operator1"
    
    result = discover(aid_txt, atf_txt, "example.com", dnssec_aid=False, dnssec_atf=False)
    
    print(f"  Domain: example.com")
    print(f"  Discovery mode: {result.discovery_mode.value} (no DNSSEC)")
    print(f"  Base grade: B → After penalty: {result.grade_after_penalty}")
    print(f"  Issues: {result.issues}")
    print()


def scenario_revoked():
    """Revoked agent — trust permanently dead."""
    print("=== Scenario: Revoked Agent ===")
    
    aid_txt = "v=aid1;p=mcp;u=https://api.bad-agent.com/mcp;s=Bad Agent"
    atf_txt = "v=atf1;gh=deadbeef;ts=REVOKED;wci=0.0;eg=F;dm=DANE;tr=200;oid=bad_operator"
    
    result = discover(aid_txt, atf_txt, "bad-agent.com", dnssec_aid=True, dnssec_atf=True)
    
    print(f"  Domain: bad-agent.com")
    print(f"  Trust state: REVOKED")
    print(f"  Grade: {result.grade_after_penalty}")
    print(f"  Issues: {result.issues}")
    print()


def scenario_verified_not_trusted():
    """VERIFIED but not TRUSTED — the DigiNotar lesson."""
    print("=== Scenario: VERIFIED but NOT TRUSTED (DigiNotar Pattern) ===")
    
    aid_txt = "v=aid1;p=mcp;u=https://api.shiny.com/mcp;k=validEd25519Key123;i=g1;s=Shiny Agent"
    atf_txt = "v=atf1;gh=fresh123;ts=ACTIVE;wci=0.15;eg=D;dm=DANE;tr=3;oid=new_operator"
    
    result = discover(aid_txt, atf_txt, "shiny.com", dnssec_aid=True, dnssec_atf=True)
    
    print(f"  Domain: shiny.com")
    print(f"  Verification: {result.verification_level.value}")
    print(f"  Verified by: {result.verified_by}")
    print(f"  Trusted score: {result.trusted_score} (cold start)")
    print(f"  Grade: {result.grade_after_penalty}")
    print(f"  KEY INSIGHT: Crypto is valid (PKA + genesis). Trust is low (3 receipts).")
    print(f"  DigiNotar lesson: VERIFIED ≠ TRUSTED. Two fields, two semantics.")
    print()


if __name__ == "__main__":
    print("AID-ATF Bridge — DNS-First Agent Identity + Trust Discovery")
    print("Per santaclawd V1.2 gap #4 + AID v1.2 spec (agentcommunity.org)")
    print("=" * 70)
    print()
    print("Two DNS records, two layers:")
    print("  _agent.<domain> = AID identity (who, endpoint, protocol)")
    print("  _atf.<domain>   = ATF trust (grade, Wilson CI, state, genesis)")
    print()
    print(f"SPEC_CONSTANTS: MIN_TRUST_TTL={MIN_TRUST_TTL}s, DNSSEC_REQUIRED_ATF={DNSSEC_REQUIRED_ATF}")
    print()
    
    scenario_full_integration()
    scenario_aid_only()
    scenario_no_dnssec()
    scenario_revoked()
    scenario_verified_not_trusted()
    
    print("=" * 70)
    print("KEY INSIGHT: VERIFIED ≠ TRUSTED.")
    print("VERIFIED = cryptographic (key valid, sig checks out).")
    print("TRUSTED = social (receipts earned, counterparties diverse, Wilson CI).")
    print("DigiNotar had valid certs from untrustworthy CA.")
    print("ATF V1.2 MUST name this distinction: verified_by + trusted_score.")
