#!/usr/bin/env python3
"""
atf-dane-pinner.py — DANE TLSA record validation for ATF registry cert pinning.

Per santaclawd: ATF V1.2 trust chain uses DNS TXT for discovery.
Without DNSSEC, DNS is spoofable. DANE (RFC 6698) pins the registry cert
hash in DNS, so discovery + cert pinning use the same infrastructure.

Three validation layers (zero new trust roots):
  1. _atf.<domain> TXT → endpoint URL (DMARC model)
  2. _443._tcp.<domain> TLSA → cert hash pin (DANE model)
  3. CT log → cert transparency (CT model)

If all three agree, discovery is reliable.
If any disagree, MITM or misconfiguration detected.

APNIC (2025): only 5.7% of domains have valid DNSSEC.
Without DNSSEC, DANE falls back to TOFU (trust on first use).
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TLSAUsage(Enum):
    """RFC 6698 Section 2.1.1 — Certificate Usage Field."""
    CA_CONSTRAINT = 0        # Pin to CA that issued cert (PKIX-TA)
    SERVICE_CONSTRAINT = 1   # Pin to specific cert (PKIX-EE)
    TRUST_ANCHOR = 2         # Pin to self-signed CA (DANE-TA)
    DOMAIN_ISSUED = 3        # Pin to domain cert, no PKIX needed (DANE-EE)


class TLSASelector(Enum):
    """RFC 6698 Section 2.1.2 — Selector Field."""
    FULL_CERT = 0            # Hash entire certificate
    SUBJECT_PK = 1           # Hash SubjectPublicKeyInfo only


class TLSAMatchType(Enum):
    """RFC 6698 Section 2.1.3 — Matching Type Field."""
    EXACT = 0                # No hash, exact match
    SHA256 = 1               # SHA-256
    SHA512 = 2               # SHA-512


class DiscoveryResult(Enum):
    VERIFIED = "VERIFIED"            # All three layers agree
    PARTIAL = "PARTIAL"              # TXT + TLSA match, no CT
    TOFU = "TOFU"                    # No DNSSEC, trust on first use
    MISMATCH = "MISMATCH"            # Layers disagree
    MISSING = "MISSING"              # No records found
    HIJACKED = "HIJACKED"            # Evidence of active attack


@dataclass
class TLSARecord:
    """DANE TLSA record: _port._proto.domain."""
    usage: TLSAUsage
    selector: TLSASelector
    match_type: TLSAMatchType
    cert_hash: str
    domain: str
    port: int = 443
    dnssec_valid: bool = False


@dataclass
class ATFDiscovery:
    """Complete ATF V1.2 discovery result."""
    domain: str
    txt_endpoint: Optional[str] = None
    txt_registry_hash: Optional[str] = None
    tlsa_record: Optional[TLSARecord] = None
    ct_cert_hash: Optional[str] = None
    actual_cert_hash: Optional[str] = None
    result: DiscoveryResult = DiscoveryResult.MISSING
    checks: list = field(default_factory=list)
    timestamp: float = 0.0


def hash_cert(cert_data: str, match_type: TLSAMatchType = TLSAMatchType.SHA256) -> str:
    """Hash certificate data per TLSA matching type."""
    if match_type == TLSAMatchType.SHA256:
        return hashlib.sha256(cert_data.encode()).hexdigest()
    elif match_type == TLSAMatchType.SHA512:
        return hashlib.sha512(cert_data.encode()).hexdigest()
    else:
        return cert_data  # EXACT match


def validate_tlsa(record: TLSARecord, actual_cert: str) -> dict:
    """Validate TLSA record against actual certificate."""
    actual_hash = hash_cert(actual_cert, record.match_type)
    match = record.cert_hash == actual_hash
    
    return {
        "match": match,
        "usage": record.usage.name,
        "selector": record.selector.name,
        "match_type": record.match_type.name,
        "expected_hash": record.cert_hash[:16] + "...",
        "actual_hash": actual_hash[:16] + "...",
        "dnssec": record.dnssec_valid,
        "security_level": "DANE" if record.dnssec_valid else "TOFU"
    }


def discover_atf_registry(
    domain: str,
    txt_endpoint: Optional[str],
    txt_registry_hash: Optional[str],
    tlsa_record: Optional[TLSARecord],
    ct_cert_hash: Optional[str],
    actual_cert: str
) -> ATFDiscovery:
    """
    Three-layer ATF registry discovery and validation.
    
    Layer 1: _atf.<domain> TXT → endpoint URL + registry hash
    Layer 2: _443._tcp.<domain> TLSA → cert pin
    Layer 3: CT log → cert transparency entry
    """
    discovery = ATFDiscovery(
        domain=domain,
        txt_endpoint=txt_endpoint,
        txt_registry_hash=txt_registry_hash,
        tlsa_record=tlsa_record,
        ct_cert_hash=ct_cert_hash,
        actual_cert_hash=hash_cert(actual_cert),
        timestamp=time.time()
    )
    
    checks = []
    
    # Layer 1: TXT record
    if txt_endpoint:
        checks.append({"layer": "TXT", "status": "FOUND", "endpoint": txt_endpoint})
    else:
        checks.append({"layer": "TXT", "status": "MISSING"})
    
    # Layer 2: TLSA record
    if tlsa_record:
        tlsa_result = validate_tlsa(tlsa_record, actual_cert)
        checks.append({
            "layer": "TLSA",
            "status": "MATCH" if tlsa_result["match"] else "MISMATCH",
            "security": tlsa_result["security_level"],
            "dnssec": tlsa_result["dnssec"]
        })
    else:
        checks.append({"layer": "TLSA", "status": "MISSING"})
    
    # Layer 3: CT log
    actual_hash = hash_cert(actual_cert)
    if ct_cert_hash:
        ct_match = ct_cert_hash == actual_hash
        checks.append({
            "layer": "CT",
            "status": "MATCH" if ct_match else "MISMATCH"
        })
    else:
        checks.append({"layer": "CT", "status": "MISSING"})
    
    discovery.checks = checks
    
    # Determine overall result
    txt_ok = txt_endpoint is not None
    tlsa_ok = tlsa_record and validate_tlsa(tlsa_record, actual_cert)["match"]
    ct_ok = ct_cert_hash and ct_cert_hash == actual_hash
    dnssec = tlsa_record.dnssec_valid if tlsa_record else False
    
    if txt_ok and tlsa_ok and ct_ok:
        discovery.result = DiscoveryResult.VERIFIED
    elif txt_ok and tlsa_ok and not ct_ok:
        discovery.result = DiscoveryResult.PARTIAL
    elif txt_ok and not tlsa_ok and not dnssec:
        discovery.result = DiscoveryResult.TOFU
    elif txt_ok and tlsa_record and not validate_tlsa(tlsa_record, actual_cert)["match"]:
        discovery.result = DiscoveryResult.HIJACKED
    elif not txt_ok:
        discovery.result = DiscoveryResult.MISSING
    else:
        discovery.result = DiscoveryResult.MISMATCH
    
    return discovery


def print_discovery(d: ATFDiscovery):
    """Pretty-print discovery result."""
    print(f"  Domain: {d.domain}")
    print(f"  Result: {d.result.value}")
    for check in d.checks:
        layer = check['layer']
        status = check['status']
        extra = ""
        if 'security' in check:
            extra = f" ({check['security']})"
        if 'endpoint' in check:
            extra = f" → {check['endpoint']}"
        print(f"    {layer}: {status}{extra}")
    print()


# === Scenarios ===

def scenario_full_verification():
    """All three layers agree — VERIFIED."""
    print("=== Scenario: Full Three-Layer Verification ===")
    cert = "registry.example.com:cert:2026-03-24"
    cert_hash = hash_cert(cert)
    
    tlsa = TLSARecord(
        usage=TLSAUsage.DOMAIN_ISSUED,
        selector=TLSASelector.FULL_CERT,
        match_type=TLSAMatchType.SHA256,
        cert_hash=cert_hash,
        domain="registry.example.com",
        dnssec_valid=True
    )
    
    d = discover_atf_registry(
        domain="registry.example.com",
        txt_endpoint="https://registry.example.com/atf/v1",
        txt_registry_hash="abc123",
        tlsa_record=tlsa,
        ct_cert_hash=cert_hash,
        actual_cert=cert
    )
    print_discovery(d)


def scenario_no_dnssec():
    """No DNSSEC — falls back to TOFU."""
    print("=== Scenario: No DNSSEC — TOFU Fallback ===")
    cert = "registry.nodane.com:cert:2026"
    
    d = discover_atf_registry(
        domain="registry.nodane.com",
        txt_endpoint="https://registry.nodane.com/atf",
        txt_registry_hash="def456",
        tlsa_record=None,  # No TLSA = no DANE
        ct_cert_hash=None,
        actual_cert=cert
    )
    print_discovery(d)
    print("  APNIC 2025: only 5.7% of domains have valid DNSSEC.")
    print("  Without DNSSEC, DANE is just DNS. TOFU is the fallback.")
    print()


def scenario_mitm_detected():
    """TLSA hash doesn't match actual cert — HIJACKED."""
    print("=== Scenario: MITM Detected — Cert Mismatch ===")
    real_cert = "registry.target.com:cert:real"
    fake_cert = "registry.target.com:cert:ATTACKER"
    real_hash = hash_cert(real_cert)
    
    tlsa = TLSARecord(
        usage=TLSAUsage.DOMAIN_ISSUED,
        selector=TLSASelector.FULL_CERT,
        match_type=TLSAMatchType.SHA256,
        cert_hash=real_hash,  # DNS has the real hash
        domain="registry.target.com",
        dnssec_valid=True
    )
    
    d = discover_atf_registry(
        domain="registry.target.com",
        txt_endpoint="https://registry.target.com/atf",
        txt_registry_hash="ghi789",
        tlsa_record=tlsa,
        ct_cert_hash=real_hash,
        actual_cert=fake_cert  # But we're seeing the attacker's cert!
    )
    print_discovery(d)
    print("  DANE caught the MITM: TLSA pin ≠ presented cert.")
    print("  CT log confirms: real cert exists, this is a different one.")
    print()


def scenario_ct_only():
    """TLSA matches but no CT entry — suspicious."""
    print("=== Scenario: No CT Entry — PARTIAL ===")
    cert = "registry.new.com:cert:fresh"
    cert_hash = hash_cert(cert)
    
    tlsa = TLSARecord(
        usage=TLSAUsage.DOMAIN_ISSUED,
        selector=TLSASelector.FULL_CERT,
        match_type=TLSAMatchType.SHA256,
        cert_hash=cert_hash,
        domain="registry.new.com",
        dnssec_valid=True
    )
    
    d = discover_atf_registry(
        domain="registry.new.com",
        txt_endpoint="https://registry.new.com/atf",
        txt_registry_hash="jkl012",
        tlsa_record=tlsa,
        ct_cert_hash=None,  # Not in CT yet
        actual_cert=cert
    )
    print_discovery(d)
    print("  TXT + TLSA agree, but no CT confirmation.")
    print("  PARTIAL = usable but monitor for CT appearance.")
    print()


if __name__ == "__main__":
    print("ATF DANE Pinner — TLSA Record Validation for Registry Cert Pinning")
    print("Per santaclawd V1.2 + RFC 6698 (DANE)")
    print("=" * 70)
    print()
    print("Three layers, zero new trust roots:")
    print("  1. _atf.<domain> TXT → endpoint (DMARC)")
    print("  2. _443._tcp.<domain> TLSA → cert pin (DANE)")
    print("  3. CT log → transparency (Certificate Transparency)")
    print()
    
    scenario_full_verification()
    scenario_no_dnssec()
    scenario_mitm_detected()
    scenario_ct_only()
    
    print("=" * 70)
    print("KEY INSIGHT: DANE without DNSSEC = DNS without security.")
    print("5.7% DNSSEC adoption (APNIC 2025) means 94.3% fall back to TOFU.")
    print("CT log as independent check: if cert is in CT but TLSA mismatches,")
    print("attacker has DNS but not the CA. Two independent paths catch more.")
