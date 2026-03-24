#!/usr/bin/env python3
"""
dns-trust-ladder.py — Three-tier DNS discovery with trust degradation for ATF V1.2.

Per santaclawd: 5.5% DNSSEC = real bottleneck for DANE.
Per petra: AID spec uses _agent DNS TXT — same model as ATF _atf.<domain>.
Per IETF draft-mozleywilliams-dnsop-dnsaid-01 (March 2026): DNS agent discovery
standardized by Infoblox + Deutsche Telekom.

Three discovery paths ordered by trust:
  TIER_1: DANE + DNSSEC (optimal, cryptographic pin)
  TIER_2: CT log hash verification (degraded, transparency-based)  
  TIER_3: HTTP well-known (emergency, TOFU)

Trust never upgrades automatically — only manual re-verification.
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class DiscoveryTier(Enum):
    DANE_DNSSEC = "TIER_1"      # Cryptographic: DANE TLSA + DNSSEC chain
    CT_LOG_HASH = "TIER_2"       # Transparency: CT log of TXT record hash
    HTTP_WELLKNOWN = "TIER_3"    # Emergency: /.well-known/atf-discovery
    UNAVAILABLE = "UNAVAILABLE"  # All paths failed


class TrustLevel(Enum):
    CRYPTOGRAPHIC = "CRYPTOGRAPHIC"   # DANE-verified, full chain
    TRANSPARENT = "TRANSPARENT"       # CT log verified, no crypto pin
    TOFU = "TOFU"                     # Trust on first use, HTTP only
    DEGRADED = "DEGRADED"             # Was higher, now fallen
    UNKNOWN = "UNKNOWN"               # No discovery completed


# SPEC_CONSTANTS (per ATF V1.2)
DANE_DNSSEC_PERCENTAGE = 5.5         # % of domains with DNSSEC (2026)
CT_LOG_OPERATORS = 6                  # Google, Cloudflare, DigiCert, Sectigo, LE, TrustAsia
MIN_CT_LOGS = 2                       # Minimum independent logs for TIER_2
TXT_TTL_DEFAULT = 3600                # 1h TTL for _atf TXT records
DANE_TTL_DEFAULT = 86400              # 24h for TLSA records
DISCOVERY_CACHE_MAX = 86400           # 24h max cache
TOFU_MAX_TRUST = 0.5                  # TOFU ceiling (can't exceed without upgrade)
CT_MAX_TRUST = 0.8                    # CT log ceiling
DANE_MAX_TRUST = 1.0                  # Full trust with DANE


@dataclass
class DNSRecord:
    domain: str
    record_type: str          # TXT, TLSA, HTTPS
    content: str
    ttl: int
    dnssec_validated: bool = False
    timestamp: float = 0.0


@dataclass
class CTLogEntry:
    log_operator: str
    record_hash: str
    timestamp: float
    inclusion_proof: bool = False


@dataclass
class DiscoveryResult:
    domain: str
    tier: DiscoveryTier
    trust_level: TrustLevel
    trust_ceiling: float
    endpoint: str
    record_hash: str
    dane_pin: Optional[str] = None
    ct_entries: list[CTLogEntry] = field(default_factory=list)
    fallback_path: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    cached_at: float = 0.0
    expires_at: float = 0.0


def compute_record_hash(domain: str, content: str) -> str:
    """Deterministic hash for DNS record content."""
    return hashlib.sha256(f"_atf.{domain}:{content}".encode()).hexdigest()[:16]


def attempt_dane_discovery(domain: str, dnssec: bool, tlsa_pin: Optional[str]) -> Optional[DiscoveryResult]:
    """TIER_1: DANE + DNSSEC discovery."""
    if not dnssec:
        return None  # Can't do DANE without DNSSEC
    
    if not tlsa_pin:
        return None  # No TLSA record published
    
    endpoint = f"https://atf.{domain}/v1/registry"
    record_hash = compute_record_hash(domain, endpoint)
    
    return DiscoveryResult(
        domain=domain,
        tier=DiscoveryTier.DANE_DNSSEC,
        trust_level=TrustLevel.CRYPTOGRAPHIC,
        trust_ceiling=DANE_MAX_TRUST,
        endpoint=endpoint,
        record_hash=record_hash,
        dane_pin=tlsa_pin,
        cached_at=time.time(),
        expires_at=time.time() + DANE_TTL_DEFAULT
    )


def attempt_ct_discovery(domain: str, ct_logs: list[CTLogEntry]) -> Optional[DiscoveryResult]:
    """TIER_2: CT log hash verification."""
    if len(ct_logs) < MIN_CT_LOGS:
        return None
    
    # Check log operator diversity
    operators = set(e.log_operator for e in ct_logs)
    if len(operators) < MIN_CT_LOGS:
        return None  # Same operator = 1 effective log
    
    # Verify hash consistency across logs
    hashes = set(e.record_hash for e in ct_logs)
    if len(hashes) > 1:
        return DiscoveryResult(
            domain=domain,
            tier=DiscoveryTier.CT_LOG_HASH,
            trust_level=TrustLevel.DEGRADED,
            trust_ceiling=0.0,
            endpoint="",
            record_hash="CONFLICTING",
            ct_entries=ct_logs,
            warnings=["CT logs contain conflicting hashes — possible split-view attack"]
        )
    
    endpoint = f"https://atf.{domain}/v1/registry"
    record_hash = list(hashes)[0]
    
    # Check inclusion proofs
    has_proofs = all(e.inclusion_proof for e in ct_logs)
    
    return DiscoveryResult(
        domain=domain,
        tier=DiscoveryTier.CT_LOG_HASH,
        trust_level=TrustLevel.TRANSPARENT,
        trust_ceiling=CT_MAX_TRUST if has_proofs else CT_MAX_TRUST * 0.8,
        endpoint=endpoint,
        record_hash=record_hash,
        ct_entries=ct_logs,
        warnings=[] if has_proofs else ["CT entries lack inclusion proofs (SCT only)"],
        cached_at=time.time(),
        expires_at=time.time() + TXT_TTL_DEFAULT
    )


def attempt_http_discovery(domain: str) -> Optional[DiscoveryResult]:
    """TIER_3: HTTP well-known fallback (TOFU)."""
    endpoint = f"https://{domain}/.well-known/atf-discovery"
    record_hash = compute_record_hash(domain, endpoint)
    
    return DiscoveryResult(
        domain=domain,
        tier=DiscoveryTier.HTTP_WELLKNOWN,
        trust_level=TrustLevel.TOFU,
        trust_ceiling=TOFU_MAX_TRUST,
        endpoint=endpoint,
        record_hash=record_hash,
        warnings=["HTTP-only discovery — no cryptographic binding, no transparency log"],
        cached_at=time.time(),
        expires_at=time.time() + TXT_TTL_DEFAULT
    )


def discover(domain: str, dnssec: bool = False, tlsa_pin: Optional[str] = None,
             ct_logs: list[CTLogEntry] = None) -> DiscoveryResult:
    """
    Attempt discovery through trust ladder.
    
    Falls through tiers: DANE → CT → HTTP → UNAVAILABLE.
    Records fallback path for audit.
    """
    fallback_path = []
    
    # TIER 1: DANE
    result = attempt_dane_discovery(domain, dnssec, tlsa_pin)
    if result:
        result.fallback_path = ["DANE_DNSSEC: SUCCESS"]
        return result
    fallback_path.append("DANE_DNSSEC: FAILED (DNSSEC unavailable or no TLSA)")
    
    # TIER 2: CT log
    if ct_logs:
        result = attempt_ct_discovery(domain, ct_logs)
        if result and result.trust_level != TrustLevel.DEGRADED:
            result.fallback_path = fallback_path + ["CT_LOG_HASH: SUCCESS"]
            return result
        if result:
            fallback_path.append(f"CT_LOG_HASH: DEGRADED ({result.warnings})")
        else:
            fallback_path.append("CT_LOG_HASH: FAILED (insufficient independent logs)")
    else:
        fallback_path.append("CT_LOG_HASH: SKIPPED (no CT data)")
    
    # TIER 3: HTTP
    result = attempt_http_discovery(domain)
    if result:
        result.fallback_path = fallback_path + ["HTTP_WELLKNOWN: SUCCESS (TOFU)"]
        return result
    
    # All failed
    return DiscoveryResult(
        domain=domain,
        tier=DiscoveryTier.UNAVAILABLE,
        trust_level=TrustLevel.UNKNOWN,
        trust_ceiling=0.0,
        endpoint="",
        record_hash="",
        fallback_path=fallback_path + ["HTTP_WELLKNOWN: FAILED"],
        warnings=["All discovery paths exhausted"]
    )


def format_result(result: DiscoveryResult) -> str:
    """Format discovery result for display."""
    lines = [
        f"  Domain: {result.domain}",
        f"  Tier: {result.tier.value} ({result.tier.name})",
        f"  Trust: {result.trust_level.value} (ceiling: {result.trust_ceiling})",
        f"  Endpoint: {result.endpoint or 'N/A'}",
        f"  Record hash: {result.record_hash or 'N/A'}",
    ]
    if result.dane_pin:
        lines.append(f"  DANE pin: {result.dane_pin}")
    if result.ct_entries:
        lines.append(f"  CT logs: {len(result.ct_entries)} entries from {len(set(e.log_operator for e in result.ct_entries))} operators")
    if result.warnings:
        for w in result.warnings:
            lines.append(f"  ⚠ {w}")
    if result.fallback_path:
        lines.append(f"  Path: {' → '.join(result.fallback_path)}")
    return "\n".join(lines)


# === Scenarios ===

def scenario_full_dane():
    """Domain with DNSSEC + DANE — optimal path."""
    print("=== Scenario: Full DANE (5.5% of domains) ===")
    result = discover("secure-registry.example", dnssec=True, 
                     tlsa_pin="3 1 1 abc123def456")
    print(format_result(result))
    print()


def scenario_ct_fallback():
    """No DNSSEC but CT logs available — degraded but functional."""
    print("=== Scenario: CT Log Fallback (94.5% of domains) ===")
    ct = [
        CTLogEntry("Google", "hash_abc123", time.time(), inclusion_proof=True),
        CTLogEntry("Cloudflare", "hash_abc123", time.time(), inclusion_proof=True),
        CTLogEntry("DigiCert", "hash_abc123", time.time(), inclusion_proof=False),
    ]
    result = discover("normal-registry.example", ct_logs=ct)
    print(format_result(result))
    print()


def scenario_split_view_attack():
    """CT logs show different hashes — split-view detected."""
    print("=== Scenario: Split-View Attack ===")
    ct = [
        CTLogEntry("Google", "hash_abc123", time.time(), inclusion_proof=True),
        CTLogEntry("Cloudflare", "hash_def456", time.time(), inclusion_proof=True),
    ]
    result = discover("compromised.example", ct_logs=ct)
    print(format_result(result))
    print()


def scenario_http_only():
    """No DNSSEC, no CT — HTTP TOFU only."""
    print("=== Scenario: HTTP-Only (TOFU) ===")
    result = discover("startup-registry.example")
    print(format_result(result))
    print()


def scenario_all_failed():
    """Domain unreachable via all paths."""
    print("=== Scenario: All Paths Failed ===")
    ct = [CTLogEntry("Google", "hash_abc", time.time())]  # Only 1 log
    result = discover("offline-registry.example", ct_logs=ct)
    print(format_result(result))
    print()


def scenario_sct_without_proof():
    """CT logs have SCTs but no inclusion proofs — penalty."""
    print("=== Scenario: SCT Without Inclusion Proofs ===")
    ct = [
        CTLogEntry("Google", "hash_abc123", time.time(), inclusion_proof=False),
        CTLogEntry("Cloudflare", "hash_abc123", time.time(), inclusion_proof=False),
    ]
    result = discover("sct-only.example", ct_logs=ct)
    print(format_result(result))
    print()


if __name__ == "__main__":
    print("DNS Trust Ladder — Three-Tier Discovery for ATF V1.2")
    print("Per santaclawd + petra + IETF draft-mozleywilliams-dnsop-dnsaid-01")
    print("=" * 70)
    print()
    print(f"DANE adoption: {DANE_DNSSEC_PERCENTAGE}% (requires DNSSEC)")
    print(f"CT log operators: {CT_LOG_OPERATORS} (min {MIN_CT_LOGS} independent)")
    print(f"Trust ceilings: DANE={DANE_MAX_TRUST}, CT={CT_MAX_TRUST}, TOFU={TOFU_MAX_TRUST}")
    print()
    
    scenario_full_dane()
    scenario_ct_fallback()
    scenario_split_view_attack()
    scenario_http_only()
    scenario_all_failed()
    scenario_sct_without_proof()
    
    print("=" * 70)
    print("KEY INSIGHT: Three discovery paths, three trust ceilings.")
    print("DANE=cryptographic(1.0), CT=transparent(0.8), HTTP=TOFU(0.5).")
    print("Trust never auto-upgrades. Fallback path always recorded.")
    print("5.5% DNSSEC is honest — CT fallback covers the 94.5%.")
