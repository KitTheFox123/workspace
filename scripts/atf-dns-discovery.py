#!/usr/bin/env python3
"""
atf-dns-discovery.py — Cross-registry discovery via DNS TXT for ATF V1.2.

Per santaclawd: _atf.<domain> DNS TXT → endpoint + assurance level.
DMARC (RFC 7489) model: self-service discovery, no central authority.
DANE (RFC 6698) for pinning: requires DNSSEC, graceful degradation without.

Discovery stack:
  1. _atf.<domain> TXT → endpoint URL + assurance level + registry_hash
  2. DANE TLSA pin (if DNSSEC) → no MITM on discovery
  3. CT log audit → anyone can verify TXT changes
  4. SMTP bootstrap → first cross-signing handshake

Key insight: DMARC succeeded because it degrades gracefully without DNSSEC.
DANE adoption is 5.5% of .com (APNIC 2024). ATF must not require it.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AssuranceLevel(Enum):
    """FBCA-style assurance levels for cross-registry trust."""
    RUDIMENTARY = "rudimentary"     # TXT exists, no verification
    BASIC = "basic"                  # TXT + SMTP reachable
    MEDIUM = "medium"                # TXT + DANE pin OR CT audited
    HIGH = "high"                    # TXT + DANE + CT + cross-signed


class DiscoveryMethod(Enum):
    DNS_TXT = "dns_txt"             # _atf.<domain> TXT record
    DANE_TLSA = "dane_tlsa"         # DNSSEC-secured pin
    CT_AUDIT = "ct_audit"           # Certificate Transparency log
    SMTP_BOOTSTRAP = "smtp_bootstrap"  # First-contact handshake
    MANUAL = "manual"               # Out-of-band exchange


class PinStatus(Enum):
    PINNED = "PINNED"               # DANE TLSA verified
    TOFU = "TOFU"                   # Trust on first use (no DNSSEC)
    CT_VERIFIED = "CT_VERIFIED"     # CT log confirms TXT
    UNVERIFIED = "UNVERIFIED"       # No verification available


# SPEC_CONSTANTS
TXT_PREFIX = "_atf"
TXT_VERSION = "ATFv1"
MIN_TTL_SECONDS = 3600              # 1 hour minimum
MAX_TTL_SECONDS = 86400 * 30        # 30 days maximum
DISCOVERY_TIMEOUT_SECONDS = 30
BOOTSTRAP_GRACE_HOURS = 72          # Time for first cross-sign after discovery


@dataclass
class ATFRecord:
    """Parsed _atf.<domain> DNS TXT record."""
    domain: str
    version: str = "ATFv1"
    endpoint: str = ""               # Registry API endpoint
    registry_hash: str = ""          # Hash of registry genesis
    assurance: str = "rudimentary"   # Assurance level claimed
    contact: str = ""                # Operator contact (email)
    cross_sign_policy: str = "open"  # open|restricted|closed
    ttl: int = 3600
    dnssec: bool = False
    dane_pin: Optional[str] = None
    ct_logged: bool = False
    discovered_at: float = 0.0
    
    def to_txt(self) -> str:
        """Generate DNS TXT record string."""
        parts = [
            f"v={self.version}",
            f"endpoint={self.endpoint}",
            f"rh={self.registry_hash}",
            f"assurance={self.assurance}",
            f"contact={self.contact}",
            f"xsign={self.cross_sign_policy}"
        ]
        return "; ".join(parts)
    
    @classmethod
    def from_txt(cls, domain: str, txt: str, dnssec: bool = False) -> "ATFRecord":
        """Parse DNS TXT record."""
        fields = {}
        for part in txt.split(";"):
            part = part.strip()
            if "=" in part:
                k, v = part.split("=", 1)
                fields[k.strip()] = v.strip()
        
        return cls(
            domain=domain,
            version=fields.get("v", "ATFv1"),
            endpoint=fields.get("endpoint", ""),
            registry_hash=fields.get("rh", ""),
            assurance=fields.get("assurance", "rudimentary"),
            contact=fields.get("contact", ""),
            cross_sign_policy=fields.get("xsign", "open"),
            dnssec=dnssec,
            discovered_at=time.time()
        )


@dataclass
class DiscoveryResult:
    """Result of cross-registry discovery attempt."""
    source_domain: str
    target_domain: str
    record: Optional[ATFRecord]
    methods_tried: list[DiscoveryMethod]
    methods_succeeded: list[DiscoveryMethod]
    pin_status: PinStatus
    assurance_verified: AssuranceLevel
    bridge_eligible: bool
    issues: list[str] = field(default_factory=list)


def discover_registry(source: str, target_domain: str, 
                      txt_exists: bool = True, dnssec: bool = False,
                      dane_pin: Optional[str] = None,
                      ct_logged: bool = False,
                      smtp_reachable: bool = True) -> DiscoveryResult:
    """
    Attempt cross-registry discovery.
    
    Simulates the discovery stack:
    1. DNS TXT lookup
    2. DANE TLSA verification (if DNSSEC)
    3. CT log audit
    4. SMTP bootstrap
    """
    methods_tried = []
    methods_succeeded = []
    issues = []
    record = None
    
    # Step 1: DNS TXT lookup
    methods_tried.append(DiscoveryMethod.DNS_TXT)
    if txt_exists:
        methods_succeeded.append(DiscoveryMethod.DNS_TXT)
        record = ATFRecord(
            domain=target_domain,
            endpoint=f"https://atf.{target_domain}/api/v1",
            registry_hash=hashlib.sha256(target_domain.encode()).hexdigest()[:16],
            assurance="medium" if dnssec else "basic",
            contact=f"operator@{target_domain}",
            cross_sign_policy="open",
            dnssec=dnssec,
            ct_logged=ct_logged,
            discovered_at=time.time()
        )
    else:
        issues.append(f"No _atf.{target_domain} TXT record found")
    
    # Step 2: DANE TLSA (requires DNSSEC)
    if dnssec:
        methods_tried.append(DiscoveryMethod.DANE_TLSA)
        if dane_pin:
            methods_succeeded.append(DiscoveryMethod.DANE_TLSA)
            if record:
                record.dane_pin = dane_pin
        else:
            issues.append("DNSSEC present but no DANE TLSA record")
    
    # Step 3: CT log audit
    if record:
        methods_tried.append(DiscoveryMethod.CT_AUDIT)
        if ct_logged:
            methods_succeeded.append(DiscoveryMethod.CT_AUDIT)
            record.ct_logged = True
        else:
            issues.append("TXT record not found in CT audit log")
    
    # Step 4: SMTP bootstrap
    if record:
        methods_tried.append(DiscoveryMethod.SMTP_BOOTSTRAP)
        if smtp_reachable:
            methods_succeeded.append(DiscoveryMethod.SMTP_BOOTSTRAP)
        else:
            issues.append(f"SMTP bootstrap to {target_domain} failed")
    
    # Determine pin status
    if DiscoveryMethod.DANE_TLSA in methods_succeeded:
        pin_status = PinStatus.PINNED
    elif DiscoveryMethod.CT_AUDIT in methods_succeeded:
        pin_status = PinStatus.CT_VERIFIED
    elif DiscoveryMethod.DNS_TXT in methods_succeeded:
        pin_status = PinStatus.TOFU
    else:
        pin_status = PinStatus.UNVERIFIED
    
    # Verify assurance level
    if pin_status == PinStatus.PINNED and ct_logged:
        assurance = AssuranceLevel.HIGH
    elif pin_status in (PinStatus.PINNED, PinStatus.CT_VERIFIED):
        assurance = AssuranceLevel.MEDIUM
    elif pin_status == PinStatus.TOFU and smtp_reachable:
        assurance = AssuranceLevel.BASIC
    elif txt_exists:
        assurance = AssuranceLevel.RUDIMENTARY
    else:
        assurance = AssuranceLevel.RUDIMENTARY
    
    # Bridge eligibility: need at least BASIC + SMTP
    bridge_eligible = (
        assurance.value in ("basic", "medium", "high") and
        DiscoveryMethod.SMTP_BOOTSTRAP in methods_succeeded
    )
    
    return DiscoveryResult(
        source_domain=source,
        target_domain=target_domain,
        record=record,
        methods_tried=methods_tried,
        methods_succeeded=methods_succeeded,
        pin_status=pin_status,
        assurance_verified=assurance,
        bridge_eligible=bridge_eligible,
        issues=issues
    )


def compute_bridge_assurance(source_assurance: AssuranceLevel, 
                              target_assurance: AssuranceLevel) -> AssuranceLevel:
    """
    Bridge assurance = MIN(source, target).
    FBCA calls this 'assurance mapping' — bridge never exceeds weakest party.
    """
    levels = [AssuranceLevel.RUDIMENTARY, AssuranceLevel.BASIC, 
              AssuranceLevel.MEDIUM, AssuranceLevel.HIGH]
    source_idx = levels.index(source_assurance)
    target_idx = levels.index(target_assurance)
    return levels[min(source_idx, target_idx)]


# === Scenarios ===

def scenario_full_stack():
    """Full discovery stack: TXT + DNSSEC + DANE + CT + SMTP."""
    print("=== Scenario: Full Stack Discovery (DNSSEC + DANE + CT) ===")
    result = discover_registry(
        "registry-a.example", "registry-b.example",
        txt_exists=True, dnssec=True, dane_pin="sha256:abc123", 
        ct_logged=True, smtp_reachable=True
    )
    print(f"  Methods tried:    {[m.value for m in result.methods_tried]}")
    print(f"  Methods succeeded:{[m.value for m in result.methods_succeeded]}")
    print(f"  Pin status:       {result.pin_status.value}")
    print(f"  Assurance:        {result.assurance_verified.value}")
    print(f"  Bridge eligible:  {result.bridge_eligible}")
    print(f"  TXT record:       {result.record.to_txt()[:80]}...")
    print()


def scenario_no_dnssec():
    """No DNSSEC — graceful degradation to TOFU."""
    print("=== Scenario: No DNSSEC (Graceful Degradation) ===")
    result = discover_registry(
        "registry-a.example", "registry-c.example",
        txt_exists=True, dnssec=False, ct_logged=True, smtp_reachable=True
    )
    print(f"  DNSSEC:           False (5.5% of .com — APNIC 2024)")
    print(f"  Pin status:       {result.pin_status.value}")
    print(f"  Assurance:        {result.assurance_verified.value}")
    print(f"  Bridge eligible:  {result.bridge_eligible}")
    print(f"  Key: degrades to CT_VERIFIED, not UNVERIFIED")
    print()


def scenario_no_txt():
    """No TXT record — undiscoverable."""
    print("=== Scenario: No TXT Record ===")
    result = discover_registry(
        "registry-a.example", "unknown-registry.example",
        txt_exists=False, smtp_reachable=False
    )
    print(f"  Methods succeeded:{[m.value for m in result.methods_succeeded]}")
    print(f"  Pin status:       {result.pin_status.value}")
    print(f"  Assurance:        {result.assurance_verified.value}")
    print(f"  Bridge eligible:  {result.bridge_eligible}")
    print(f"  Issues:           {result.issues}")
    print()


def scenario_bridge_assurance():
    """Bridge assurance = MIN(source, target)."""
    print("=== Scenario: Bridge Assurance Mapping ===")
    pairs = [
        (AssuranceLevel.HIGH, AssuranceLevel.HIGH, "both verified"),
        (AssuranceLevel.HIGH, AssuranceLevel.BASIC, "target weaker"),
        (AssuranceLevel.BASIC, AssuranceLevel.MEDIUM, "source weaker"),
        (AssuranceLevel.RUDIMENTARY, AssuranceLevel.HIGH, "source rudimentary"),
    ]
    for src, tgt, desc in pairs:
        bridge = compute_bridge_assurance(src, tgt)
        print(f"  {src.value:>12} + {tgt.value:<12} = {bridge.value:<12} ({desc})")
    print(f"  Key: bridge never exceeds weakest party (FBCA assurance mapping)")
    print()


def scenario_tofu_upgrade():
    """TOFU discovery → later upgraded with DANE."""
    print("=== Scenario: TOFU → DANE Upgrade Path ===")
    
    # Initial discovery: no DNSSEC
    r1 = discover_registry("a.example", "b.example",
                           txt_exists=True, dnssec=False, smtp_reachable=True)
    print(f"  Initial: pin={r1.pin_status.value}, assurance={r1.assurance_verified.value}")
    
    # Later: DNSSEC deployed
    r2 = discover_registry("a.example", "b.example",
                           txt_exists=True, dnssec=True, dane_pin="sha256:def456",
                           ct_logged=True, smtp_reachable=True)
    print(f"  Upgraded: pin={r2.pin_status.value}, assurance={r2.assurance_verified.value}")
    print(f"  Key: TOFU→PINNED is a one-way upgrade. PINNED→TOFU = downgrade alert.")
    print()


if __name__ == "__main__":
    print("ATF DNS Discovery — Cross-Registry Federation via DNS TXT")
    print("Per santaclawd + DMARC (RFC 7489) + DANE (RFC 6698)")
    print("=" * 70)
    print()
    print("Discovery stack:")
    print("  1. _atf.<domain> TXT → endpoint + assurance + registry_hash")
    print("  2. DANE TLSA pin (if DNSSEC) → no MITM")
    print("  3. CT log audit → public verifiability")
    print("  4. SMTP bootstrap → first handshake")
    print()
    
    scenario_full_stack()
    scenario_no_dnssec()
    scenario_no_txt()
    scenario_bridge_assurance()
    scenario_tofu_upgrade()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("1. No central authority needed — DNS is self-service discovery")
    print("2. DMARC succeeded because it degrades gracefully without DNSSEC")
    print("3. DANE for MUST (pinning), TOFU+CT for SHOULD (discovery)")
    print("4. Bridge assurance = MIN(source, target) — FBCA model")
    print("5. TOFU→PINNED upgrade path — deploy DNSSEC when ready")
    print(f"6. DNSSEC adoption: ~5.5% of .com (APNIC 2024) — cannot require it")
